"""The repository brief: core memory that leads every ``retrieve_context`` answer.

At most ``BRIEF_CHARS`` characters, built only from the index and from
active memory, and frozen per indexed commit (``repo_briefs``): what the
repository is, how it is laid out, its main modules, and its strongest
conventions and playbooks.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import PurePosixPath

from ..codeintel.retrieval import path_role
from ..database.models import MemoryItem, MemorySkill
from .miners import Snapshot

BRIEF_CHARS = 2200
# Which conventions lead the brief, in order (by key prefix). Per-file items
# (co-change, file origins) are shown next to the code they concern instead.
PRIORITY = ("tooling/", "commits/", "changelog/", "tests/", "naming/", "deprecation/", "exceptions/", "typing/",
            "docs/", "history/runtime/")


def first_sentence(text: str, limit: int = 220) -> str:
    end = text.find(". ")
    sentence = text if end < 0 else text[:end + 1]
    return sentence if len(sentence) <= limit else sentence[:limit - 1].rstrip() + "…"


def _brief_line(item: MemoryItem) -> str:
    if item.key.startswith("naming/") and item.title.count(": ") == 1 and not item.key.endswith("prefixes"):
        return f"{item.title} ({item.support} names, {item.confidence:.0%})"
    return first_sentence(item.body)


def _layout(snap: Snapshot) -> list[str]:
    tops: dict[str, Counter] = defaultdict(Counter)
    for path in snap.files:
        parts = PurePosixPath(path).parts
        if parts[0].startswith("."):
            continue
        top = parts[0] + "/" if len(parts) > 1 else "(root)"
        tops[top][path_role(path)] += 1
    rows = []
    for top, roles in sorted(tops.items(), key=lambda kv: -sum(kv[1].values()))[:7]:
        if top == "(root)":
            continue
        role, _ = roles.most_common(1)[0]
        rows.append(f"{top} ({role}, {sum(roles.values())} files)")
    return rows


def _main_modules(snap: Snapshot, limit: int = 6) -> list[str]:
    per_file = Counter(c.path for c in snap.source())
    methods = Counter(c.parent for c in snap.source() if c.kind == "method" and c.parent)
    # Most-called first (call-graph in-degree), then most symbols.
    order = sorted(per_file, key=lambda p: (-snap.callers.get(p, 0), -per_file[p], p))
    rows = []
    for path in order[:limit]:
        classes = sorted((c for c in snap.source() if c.path == path and c.kind == "class"),
                         key=lambda c: -methods[c.symbol])
        names = [c.name for c in classes[:4]]
        if not names:
            names = [c.name for c in snap.source() if c.path == path and c.kind in ("function", "macro")
                     and not c.name.startswith("_")][:4]
        names = list(dict.fromkeys(names))
        rows.append(f"{path}: {', '.join(names)}" if names else path)
    return rows


def compose_brief(snap: Snapshot, items: list[MemoryItem], skills: list[MemorySkill]) -> tuple[str, dict]:
    langs = Counter(c.language for c in snap.source())
    files = Counter()
    for lang, path in {(c.language, c.path) for c in snap.source()}:
        files[lang] += 1
    header = (f"# {snap.name} — repository brief (commit {snap.commit[:10]})\n"
              "Languages (source): " + ", ".join(f"{lang} {files[lang]} files / {n} symbols"
                                                 for lang, n in langs.most_common(4)) + "\n")
    sections: list[tuple[str, list[str]]] = [
        ("Layout", _layout(snap)),
        ("Main modules", _main_modules(snap)),
    ]
    ranked: list[MemoryItem] = []
    for prefix in PRIORITY:
        ranked += sorted((i for i in items if i.key.startswith(prefix) and i not in ranked),
                         key=lambda i: (-i.support, i.key))
    sections.append(("Conventions", [_brief_line(i) for i in ranked]))
    sections.append(("Playbooks", [f"{s.name}: {first_sentence(s.description, 160)}"
                                   for s in sorted(skills, key=lambda s: -s.support)[:4]]))
    text = header
    used_keys: list[str] = []
    used_skills: list[str] = []
    for title, rows in sections:
        if not rows:
            continue
        block = f"\n## {title}\n"
        for i, row in enumerate(rows):
            line = f"- {row}\n"
            if len(text) + len(block) + len(line) > BRIEF_CHARS:
                break
            block += line
            if title == "Conventions":
                used_keys.append(ranked[i].key)
            elif title == "Playbooks":
                used_skills.append(row.split(":", 1)[0])
        if block.count("\n- "):
            text += block
    return text[:BRIEF_CHARS], {"keys": used_keys, "skills": used_skills}
