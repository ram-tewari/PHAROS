"""Deterministic (L1) miners: repository facts and conventions with support counts.

Every miner reads the existing index (``document_chunks.chunk_metadata``:
path, name, parent, signature, docstring, calls), the working tree at the
indexed commit, or the full git history, so every language is covered the
same way. Rules shared by all of them:

* conventions are measured on **source** files only (``path_role``), never
  averaged with tests, docs or examples;
* every item says how many cases support it, and cites evidence PHAROS can
  re-check (lines with a hash, a file blob, a commit, the lines a commit
  changed, or a tally);
* a count is backed by a tally of what was counted (every commit, or the
  exceptions to a convention), and a path that was renamed carries the
  renames, so the claim can be checked from its evidence alone;
* an item is ``eligible`` to auto-activate only when its own rule holds
  (typically ≥ 90 % agreement over ≥ 20 cases, or an exact git event);
* nothing is called removed or abandoned unless it is absent at the
  indexed commit;
* a claim that can be tested on a change carries a :mod:`~app.learning.checks`
  predicate (``Candidate.check``); the pipeline backtests it and that record,
  not ``eligible``, decides whether it is served. Pure history facts carry no
  check and stay advisory.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..codeintel.retrieval import path_role
from .checks import (
    TEST_SUPPORT_RE,
    AddedPattern,
    Change,
    Companion,
    Forbidden,
    Message,
    Naming,
    NewFileCompanion,
    NewFileContains,
    NewTestFileLocation,
    Paths,
    Signature,
    case_style,
    test_pattern,
)
from .history import Commit, HistoryError, _git, commit_messages, commits_touching, file_at
from .memory import (
    Candidate,
    SkillCandidate,
    code_evidence,
    commit_evidence,
    diff_evidence,
    file_evidence,
    same_changelog,
    tally_evidence,
)

MIN_CASES = 20
STRONG = 0.9
MAX_EXAMPLES = 4
WINDOW = 60  # co-change and test homes count over a file's last 60 commits, all listed in the tally
FOCUSED = 10  # test homes count only commits of at most this many files


@dataclass
class Chunk:
    path: str
    kind: str
    symbol: str
    name: str
    parent: str | None
    language: str
    start: int
    end: int
    signature: str
    docstring: str
    role: str


@dataclass
class Snapshot:
    """What the miners see: one repository at one indexed commit."""

    name: str
    commit: str
    checkout: Path
    mirror: Path
    chunks: list[Chunk]
    files: set[str]
    history: list[Commit] = field(default_factory=list)
    callers: Counter = field(default_factory=Counter)  # resolved incoming call edges per file
    _lines: dict[str, list[str]] = field(default_factory=dict)
    _forward: dict[str, tuple[Commit, str]] | None = None

    def name_link(self, recorded: str, now: str) -> dict | None:
        """The renames that turned ``recorded`` into ``now``, for a tally's ``names``; None if none connect."""
        if self._forward is None:
            self._forward = {}
            for c in self.history:  # newest first: keep each name's latest rename
                for old, new in c.renames:
                    self._forward.setdefault(old, (c, new))
        hops, current = [], recorded
        while current != now and not same_changelog(current, now) and current in self._forward and len(hops) < 10:
            c, new = self._forward[current]
            hops.append({"sha": c.sha[:12], "date": c.date[:10], "from": current, "to": new})
            current = new
        if current != now and not same_changelog(current, now):
            return None
        return {"recorded": recorded, "now": now, "renames": hops}

    def lines(self, path: str) -> list[str]:
        if path not in self._lines:
            try:
                self._lines[path] = (self.checkout / path).read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                self._lines[path] = []
        return self._lines[path]

    def canonical(self, path: str) -> str:
        """A historical path under its name at the commit: an old root changelog
        (``CHANGES.rst``) counts as the current one (``CHANGES.md``) even when git
        saw no rename because the format changed."""
        if path in self.files or "/" in path or not CHANGELOG_RE.match(path):
            return path
        stem = path.split(".", 1)[0].lower()
        current = [p for p in self.files if "/" not in p and p.split(".", 1)[0].lower() == stem]
        return current[0] if len(current) == 1 else path

    def source(self, language: str | None = None) -> list[Chunk]:
        return [c for c in self.chunks if c.role == "source" and (language is None or c.language == language)]

    def evidence_at(self, chunk: Chunk, needle: str | None = None, span: int = 1) -> dict | None:
        """Lines of ``chunk`` starting at its definition (the first line containing ``needle``)."""
        lines = self.lines(chunk.path)
        start = chunk.start
        if needle:
            for i in range(chunk.start, min(chunk.end, chunk.start + 15) + 1):
                if i <= len(lines) and needle in lines[i - 1]:
                    start = i
                    break
        return code_evidence(self.checkout, chunk.path, start, min(start + span - 1, max(chunk.end, start)))


def _top(counts: Counter, n: int | None = None) -> list[tuple]:
    """``most_common`` with ties broken by name, so a run does not depend on set iteration order."""
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "0%"


def _symbols(snap: Snapshot, chunks: list[Chunk]) -> list[dict]:
    """Tally rows (path, definition line, name) for chunks, in file order."""
    rows = []
    for c in sorted(chunks, key=lambda c: (c.path, c.start)):
        lines = snap.lines(c.path)
        line = next((i for i in range(c.start, min(c.end, c.start + 40) + 1)
                     if i <= len(lines) and c.name in lines[i - 1]), None)
        if line:
            rows.append({"path": c.path, "line": line, "name": c.name})
    return rows


def _minority(snap: Snapshot, yes: tuple[str, list[Chunk]], no: tuple[str, list[Chunk]]) -> tuple:
    """The smaller side of a split as a tally group: listing it establishes the other side's count."""
    label, chunks = min(yes, no, key=lambda side: len(side[1]))
    return label, len(chunks), _symbols(snap, chunks)


def _commit_tally(snap: Snapshot, label: str, commits: list[Commit], claimed: list[str]) -> dict:
    """Every counted commit with the claimed files it touched, named as that commit recorded them."""
    wanted, rows, names = set(claimed), [], {}
    for c in commits:
        paths = []
        for _, p in c.files:
            now = snap.canonical(p)
            if now in wanted:
                raw = c.recorded(p)
                paths.append(raw)
                if raw != now:
                    names.setdefault(raw, now)
        rows.append({"sha": c.sha[:12], "date": c.date[:10], "subject": c.subject[:80], "paths": sorted(set(paths))})
    links = [link for raw, now in sorted(names.items()) if (link := snap.name_link(raw, now))]
    return tally_evidence(label, len(commits), [(label, len(commits), rows)], links)


def _line_evidence(snap: Snapshot, path: str, start: int, end: int, needle: str | re.Pattern) -> dict | None:
    """Code evidence for the first line in ``start..end`` of ``path`` that contains ``needle``."""
    lines = snap.lines(path)
    for i in range(max(1, start), min(end, len(lines)) + 1):
        if (needle.search(lines[i - 1]) if isinstance(needle, re.Pattern) else needle in lines[i - 1]):
            return code_evidence(snap.checkout, path, i, i)
    return None


def _spread(chunks: list[Chunk], k: int = MAX_EXAMPLES) -> list[Chunk]:
    """Up to k chunks from different files, deterministic."""
    seen, out = set(), []
    for c in sorted(chunks, key=lambda c: (c.path, c.start)):
        if c.path not in seen:
            seen.add(c.path)
            out.append(c)
    step = max(1, len(out) // k)
    return out[::step][:k]


# ── naming ──────────────────────────────────────────────────────────────

_KIND_WORDS = {"function": "functions", "method": "methods", "class": "classes", "macro": "macros"}


def mine_naming(snap: Snapshot) -> list[Candidate]:
    out = []
    by = defaultdict(list)
    for c in snap.source():
        if c.kind in _KIND_WORDS and c.name and not (c.name.startswith("__") and c.name.endswith("__")):
            by[(c.language, c.kind)].append(c)
    for (lang, kind), chunks in sorted(by.items()):
        styled = [(c, case_style(c.name)) for c in chunks]
        styled = [(c, s) for c, s in styled if s]
        if len(styled) < MIN_CASES:
            continue
        counts = Counter(s for _, s in styled)
        words = _KIND_WORDS[kind]
        extra = []
        if lang == "go" and kind != "macro":
            mixed = counts["camelCase"] + counts["PascalCase"]
            exported = [c for c in chunks if c.name[:1].isupper()]
            body = (f"Go {words} use MixedCaps, never underscores: {mixed} of {len(styled)} multi-part "
                    f"names ({_pct(mixed, len(styled))}). Exported names start upper-case "
                    f"({len(exported)} of {len(chunks)} {words} are exported).")
            top, n = "MixedCaps", mixed
            extra.append(_minority(snap, (f"exported, of all {len(chunks)} {words}", exported),
                                   (f"not exported, of all {len(chunks)} {words}",
                                    [c for c in chunks if not c.name[:1].isupper()])))
        else:
            top, n = _top(counts, 1)[0]
            body = (f"{lang.capitalize()} {words} in source files are {top}: {n} of {len(styled)} "
                    f"multi-part names ({_pct(n, len(styled))}).")
            private = [c for c in chunks if c.name.startswith("_") and not c.name.startswith("__")]
            if lang == "python" and private:
                body += f" Private helpers start with an underscore ({len(private)} of {len(chunks)})."
                extra.append((f"private helpers (leading underscore), of all {len(chunks)} {words}", len(private),
                              _symbols(snap, private)))
        share = n / len(styled)
        fits = {"camelCase", "PascalCase"} if top == "MixedCaps" else {top}
        examples = [c for c, s in styled if s in fits]
        others = [c for c, s in styled if s not in fits]
        evidence = [e for c in _spread(examples) if (e := snap.evidence_at(c, c.name))]
        evidence.append(tally_evidence(f"{lang} {words} with multi-part names in source files", len(styled),
                                       [(f"not {top}", len(others), _symbols(snap, others)), *extra]))
        out.append(Candidate(
            key=f"naming/{lang}/{kind}", kind="convention", title=f"{lang} {_KIND_WORDS[kind]}: {top}",
            body=body + " Examples: " + ", ".join(c.name for c in _spread(examples)) + ".",
            evidence=evidence, support=n, confidence=share, source="code",
            scope={"languages": [lang]}, eligible=share >= STRONG,
            check=Naming(language=lang, symbol=kind, style=top).to_json()))
    return out


def mine_prefixes(snap: Snapshot) -> list[Candidate]:
    """C has no namespaces, so name prefixes carry visibility and module."""
    funcs = [c for c in snap.source("c") if c.kind == "function"]
    if len(funcs) < 50:
        return []
    groups: dict[str, list[Chunk]] = defaultdict(list)
    for c in funcs:
        m = re.match(r"^([A-Za-z][A-Za-z0-9]*_)", c.name)
        if m:
            groups[m.group(1)].append(c)
    keep = sorted(((p, cs) for p, cs in groups.items() if len(cs) >= 20 and len(cs) >= 0.03 * len(funcs)),
                  key=lambda item: -len(item[1]))[:6]
    if len(keep) < 2:
        return []
    parts, evidence = [], []
    for prefix, cs in keep:
        dirs = Counter(str(PurePosixPath(c.path).parent) for c in cs).most_common(2)
        where = ", ".join(f"{d}/ {_pct(n, len(cs))}" for d, n in dirs)
        files = len({c.path for c in cs})
        parts.append(f"{prefix} {len(cs)} functions in {files} files ({where})")
        if (e := snap.evidence_at(_spread(cs, 1)[0], prefix)):
            evidence.append(e)
    static = sum(1 for c in funcs if c.signature.lstrip().startswith("static"))
    body = ("C function-name prefixes mark who may call a function: " + "; ".join(parts) + ". "
            f"{static} of {len(funcs)} functions ({_pct(static, len(funcs))}) are static (file-local).")
    support = sum(len(cs) for _, cs in keep)
    return [Candidate(key="naming/c/prefixes", kind="convention", title="C function-name prefixes",
                      body=body, evidence=evidence, support=support, confidence=support / len(funcs),
                      source="code", scope={"languages": ["c"]}, eligible=True)]


# ── documentation, typing, exceptions ──────────────────────────────────

_DIRECTIVE_RE = re.compile(r"\.\. (versionadded|versionchanged|deprecated)::")


def _public(c: Chunk) -> bool:
    if c.language == "python":
        return not c.name.startswith("_") and not (c.parent or "").rsplit(".", 1)[-1].startswith("_")
    if c.language == "go":
        return c.name[:1].isupper()
    return True


def mine_docs(snap: Snapshot) -> list[Candidate]:
    out = []
    by = defaultdict(list)
    for c in snap.source():
        if c.kind in ("function", "method", "class") and c.name and _public(c):
            by[c.language].append(c)
    for lang, chunks in sorted(by.items()):
        if len(chunks) < MIN_CASES:
            continue
        documented = [c for c in chunks if c.docstring]
        share = len(documented) / len(chunks)
        body = (f"Public {lang} functions, methods and classes are documented: {len(documented)} of {len(chunks)} "
                f"({_pct(len(documented), len(chunks))}) have a doc comment.")
        evidence = [e for c in _spread(documented, 2) if (e := snap.evidence_at(c, c.name, span=3))]
        groups = [_minority(snap, ("documented", documented), ("not documented",
                                                                [c for c in chunks if not c.docstring]))]
        if lang == "python":
            styles = {
                "reST field lists (:param x:)": (":param", ":return"),
                "Google style (Args:/Returns:)": ("Args:", "Returns:"),
                "NumPy style (Parameters ----)": ("Parameters\n", "Returns\n"),
            }
            using = {s: [c for c in documented if any(m in c.docstring for m in marks)] for s, marks in styles.items()}
            style, users = max(using.items(), key=lambda kv: len(kv[1]))
            if len(users) >= 10:
                body += f" Docstrings use {style} ({len(users)})."
                mark = styles[style][0].strip()
                evidence += [e for c in _spread(users, 2) if (e := _line_evidence(snap, c.path, c.start, c.end, mark))]
                groups.append((f"docstrings in {style}", len(users), _symbols(snap, users)))
            directives = Counter(m for c in documented for m in _DIRECTIVE_RE.findall(c.docstring))
            if sum(directives.values()) >= 5:
                body += (" API history is recorded in docstrings with Sphinx directives: "
                         + ", ".join(f".. {d}:: ({n})" for d, n in directives.most_common()) + ".")
                marked = [c for c in documented if _DIRECTIVE_RE.search(c.docstring)]
                evidence += [e for c in _spread(marked, 2)
                             if (e := _line_evidence(snap, c.path, c.start, c.end, _DIRECTIVE_RE))]
        elif lang == "go":
            named = [c for c in documented if c.docstring.startswith(c.name)]
            body += f" Doc comments start with the symbol's name ({len(named)} of {len(documented)})."
            groups.append(_minority(snap, ("doc comment starts with the name", named),
                                    ("doc comment does not start with the name",
                                     [c for c in documented if not c.docstring.startswith(c.name)])))
        evidence.append(tally_evidence(f"public {lang} functions, methods and classes", len(chunks), groups))
        out.append(Candidate(key=f"docs/{lang}", kind="convention", title=f"{lang} documentation",
                             body=body, evidence=evidence, support=len(documented), confidence=share,
                             source="code", scope={"languages": [lang]}, eligible=share >= 0.6))
    return out


def _params(signature: str) -> list[str]:
    inner = signature[signature.find("(") + 1:]
    depth, cur, out = 0, "", []
    for ch in inner:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    out.append(cur.strip())
    return [p for p in out if p and p not in ("*", "/")
            and p.split(":")[0].split("=")[0].strip().lstrip("*") not in ("self", "cls")]


def mine_python_typing(snap: Snapshot) -> list[Candidate]:
    funcs = [c for c in snap.source("python") if c.kind in ("function", "method") and c.signature.startswith(
        ("def ", "async def "))]
    out = []
    if len(funcs) >= MIN_CASES:
        returns = sum("->" in c.signature for c in funcs)
        params = [p for c in funcs for p in _params(c.signature)]
        annotated = sum(":" in p for p in params)
        share = returns / len(funcs)
        body = (f"Python source is type-annotated: {returns} of {len(funcs)} functions ({_pct(returns, len(funcs))}) "
                f"declare a return type and {annotated} of {len(params)} parameters "
                f"({_pct(annotated, len(params))}) are annotated.")
        evidence = [e for c in _spread([c for c in funcs if "->" in c.signature])
                    if (e := snap.evidence_at(c, c.name))]
        bare = [c for c in funcs if any(":" not in p for p in _params(c.signature))]
        evidence.append(tally_evidence("Python functions and methods in source files", len(funcs), [
            _minority(snap, ("with a return type", [c for c in funcs if "->" in c.signature]),
                      ("without a return type", [c for c in funcs if "->" not in c.signature])),
            (f"functions with unannotated parameters ({len(params) - annotated} parameters in all)", len(bare),
             _symbols(snap, bare))]))
        out.append(Candidate(key="typing/python/annotations", kind="convention", title="Python type hints",
                             body=body, evidence=evidence, support=returns, confidence=share, source="code",
                             scope={"languages": ["python"]}, eligible=share >= STRONG,
                             check=Signature(language="python", symbols=("function", "method"), require=r"->",
                                             label="declare a return type (-> T)").to_json()))
    modules = sorted({c.path for c in snap.source("python")})
    if len(modules) >= 5:
        with_future = []
        for path in modules:
            for i, line in enumerate(snap.lines(path)[:60], start=1):
                if line.strip() == "from __future__ import annotations":
                    with_future.append((path, i))
                    break
        share = len(with_future) / len(modules)
        if share >= 0.5:
            evidence = [e for path, i in with_future[:: max(1, len(with_future) // MAX_EXAMPLES)][:MAX_EXAMPLES]
                        if (e := code_evidence(snap.checkout, path, i, i))]
            have = {p for p, _ in with_future}
            without = [{"path": p} for p in modules if p not in have]
            evidence.append(tally_evidence("Python source modules", len(modules),
                                           [("modules without it", len(without), without)]))
            out.append(Candidate(
                key="typing/python/future-annotations", kind="convention",
                title="from __future__ import annotations",
                body=(f"Python source modules import `from __future__ import annotations` at the top: {len(with_future)} "
                      f"of {len(modules)} ({_pct(len(with_future), len(modules))})."),
                evidence=evidence, support=len(with_future), confidence=share, source="code",
                scope={"languages": ["python"]}, eligible=share >= STRONG and len(with_future) >= 5,
                check=NewFileContains(new=Paths(globs=("**/*.py",), roles=("source",)),
                                      pattern=r"^from __future__ import annotations\s*$",
                                      label="imports `from __future__ import annotations`").to_json()))
    return out


_BUILTIN_EXC = re.compile(r"^(Base)?Exception$|Error$|Warning$|^(KeyboardInterrupt|SystemExit|StopIteration)$")


def mine_exceptions(snap: Snapshot) -> list[Candidate]:
    out = []
    for lang, pattern in (("python", r"^class\s+\w+\s*\((.*)\)"), ("typescript", r"\bextends\s+([\w.]+)"),
                          ("javascript", r"\bextends\s+([\w.]+)"), ("java", r"\bextends\s+([\w.]+)")):
        classes = [c for c in snap.source(lang) if c.kind == "class"]
        bases: dict[str, list[str]] = {}
        by_name: dict[str, Chunk] = {}
        for c in classes:
            m = re.search(pattern, c.signature)
            names = [b.strip().split("[")[0].rsplit(".", 1)[-1] for b in (m.group(1).split(",") if m else [])]
            bases[c.name] = [b for b in names if b and "=" not in b]
            by_name.setdefault(c.name, c)
        exc: set[str] = set()
        changed = True
        while changed:
            changed = False
            for name, bs in bases.items():
                if name not in exc and any(b in exc or _BUILTIN_EXC.search(b) for b in bs):
                    exc.add(name)
                    changed = True
        if len(exc) < 4:
            continue
        children = Counter(b for name in exc for b in bases[name] if b in exc)
        roots = [(name, n) for name, n in _top(children) if n >= 3]
        if not roots:
            continue
        root, n = roots[0]
        homes = Counter(str(PurePosixPath(by_name[name].path).parent) for name in exc)
        home, k = homes.most_common(1)[0]
        descendants = {root}
        grew = True
        while grew:
            grew = False
            for name in exc:
                if name not in descendants and any(b in descendants for b in bases[name]):
                    descendants.add(name)
                    grew = True
        body = (f"The project's exception classes derive from {root} (defined in {by_name[root].path}, base "
                f"{', '.join(bases[root]) or '-'}): {len(descendants) - 1} of the {len(exc)} {lang} exception "
                f"classes in source do ({k} of the {len(exc)} live in {home}/).")
        if roots[1:4]:
            body += " Other bases: " + ", ".join(f"{name} ({k})" for name, k in roots[1:4]) + "."
        ev_chunks = [by_name[root]] + _spread([by_name[x] for x in descendants if x != root], 3)
        evidence = [e for c in ev_chunks if (e := snap.evidence_at(c, c.name))]
        derived = [by_name[x] for x in descendants if x != root]
        rest = [by_name[x] for x in exc if x not in descendants]
        evidence.append(tally_evidence(f"{lang} exception classes in source (each row is its class line)", len(exc), [
            (f"derive from {root}", len(derived), _symbols(snap, derived)),
            ("other exception classes", len(rest), _symbols(snap, rest))]))
        out.append(Candidate(key=f"exceptions/{lang}", kind="convention", title=f"{lang} exception hierarchy",
                             body=body, evidence=evidence, support=len(descendants) - 1,
                             confidence=(len(descendants) - 1) / len(exc), source="code",
                             scope={"languages": [lang]}, eligible=len(descendants) - 1 >= 5))
    return out


# ── deprecation ─────────────────────────────────────────────────────────

_WARN_RE = re.compile(r"warnings\.warn\(")
_REMOVED_RE = re.compile(r"will be removed in ([A-Z][\w-]* ?\d[\w.]*|\d[\w.]*|version \d[\w.]*)")


def mine_deprecation(snap: Snapshot) -> list[Candidate]:
    out = []
    all_sites: dict[str, list[tuple[str, int]]] = {}
    by_lang: dict[str, list[str]] = defaultdict(list)
    for c in snap.source():
        if c.path not in by_lang[c.language]:
            by_lang[c.language].append(c.path)
    if by_lang.get("python"):
        sites, levels, removals = [], Counter(), Counter()
        for path in by_lang["python"]:
            lines = snap.lines(path)
            text = "\n".join(lines)
            for m in _WARN_RE.finditer(text):
                call = text[m.start():m.start() + 500]
                if "DeprecationWarning" not in call.split(")\n")[0] and "DeprecationWarning" not in call[:300]:
                    continue
                line = text.count("\n", 0, m.start()) + 1
                sites.append((path, line))
                if (lv := re.search(r"stacklevel=(\d)", call[:300])):
                    levels[lv.group(1)] += 1
                if (rm := _REMOVED_RE.search(call[:300])):
                    removals[rm.group(1)] += 1
        if len(sites) >= 3:
            files = len({p for p, _ in sites})
            call = "warnings.warn(..., DeprecationWarning)"
            counts = f"{len(sites)} sites in {files} files"
            if levels:
                level, n = _top(levels, 1)[0]
                call = f"warnings.warn(..., DeprecationWarning, stacklevel={level})"
                counts += f"; stacklevel={level} in {n}"
            body = f"Deprecations warn at runtime with `{call}` ({counts})."
            if removals:
                phrase, n = removals.most_common(1)[0]
                body += f" Messages say the old name 'will be removed in {phrase}' ({n} of {len(sites)})."
            evidence = [e for path, line in sites[:: max(1, len(sites) // MAX_EXAMPLES)][:MAX_EXAMPLES]
                        if (e := code_evidence(snap.checkout, path, line, min(line + 4, len(snap.lines(path)))))]
            rows = [{"path": p, "line": i, "name": "warnings.warn("} for p, i in sites]
            evidence.append(tally_evidence("Python DeprecationWarning sites in source", len(sites),
                                           [("warnings.warn(..., DeprecationWarning) calls", len(sites), rows)]))
            check = None
            if levels:
                check = AddedPattern(when=r"\bDeprecationWarning\b", then=rf"stacklevel\s*=\s*{level}\b",
                                     label=f"code that adds a DeprecationWarning passes stacklevel={level}",
                                     scope=Paths(roles=("source",), languages=("python",))).to_json()
            out.append(Candidate(key="deprecation/python", kind="convention", title="How Python APIs are deprecated",
                                 body=body, evidence=evidence, support=len(sites),
                                 confidence=max(levels.values(), default=len(sites)) / len(sites), source="code",
                                 scope={"languages": ["python"]}, eligible=len(sites) >= 5, check=check))
            all_sites["python"] = sites
    marks = {"go": ("// Deprecated:", "Doc comments mark deprecated Go API with a `// Deprecated:` paragraph"),
             "typescript": ("@deprecated", "Deprecated TypeScript API is marked with a `@deprecated` JSDoc tag"),
             "javascript": ("@deprecated", "Deprecated JavaScript API is marked with a `@deprecated` JSDoc tag"),
             "rust": ("#[deprecated", "Deprecated Rust items carry `#[deprecated(...)]`")}
    for lang, (needle, sentence) in marks.items():
        sites = [(p, i) for p in by_lang.get(lang, []) for i, line in enumerate(snap.lines(p), start=1)
                 if needle in line]
        if len(sites) >= 3:
            evidence = [e for p, i in sites[:MAX_EXAMPLES] if (e := code_evidence(snap.checkout, p, i, i))]
            evidence.append(tally_evidence(f"{lang} deprecation markers in source", len(sites), [
                (f"lines with {needle}", len(sites), [{"path": p, "line": i, "name": needle} for p, i in sites])]))
            out.append(Candidate(key=f"deprecation/{lang}", kind="convention", title=f"How {lang} APIs are deprecated",
                                 body=f"{sentence} ({len(sites)} sites).", evidence=evidence, support=len(sites),
                                 confidence=1.0, source="code", scope={"languages": [lang]},
                                 eligible=len(sites) >= 5,
                                 check=AddedPattern(when=r"(?i)deprecat", then=re.escape(needle),
                                                    label=f"added text about deprecation uses the {needle} marker",
                                                    scope=Paths(roles=("source",), languages=(lang,))).to_json()))
            all_sites[lang] = sites
    for lang, sites in sorted(all_sites.items()):
        if (item := _deprecated_calls(snap, lang, sites)):
            out.append(item)
    return out


def _deprecated_calls(snap: Snapshot, lang: str, sites: list[tuple[str, int]]) -> Candidate | None:
    """The deprecated functions, methods and classes themselves: new source code should not call them.

    A Python deprecation warns inside the deprecated definition; the other languages mark the doc
    comment or attribute just above it. Only distinctive names defined once are kept, so the check does
    not catch a same-named symbol elsewhere."""
    chunks = [c for c in snap.source(lang) if c.kind in ("function", "method", "class")]
    defined = Counter(c.name for c in chunks)
    by_path: dict[str, list[Chunk]] = defaultdict(list)
    for c in chunks:
        by_path[c.path].append(c)
    found: dict[str, Chunk] = {}
    for path, line in sites:
        if lang == "python":
            inside = sorted((c for c in by_path[path] if c.start < line <= c.end), key=lambda c: -c.start)
            if inside and inside[0].name in ("__init__", "__new__", "__post_init__"):
                inside = [c for c in inside[1:] if c.kind == "class"]  # the constructor warns: the class is
            target = inside[0] if inside else None
        else:
            target = min((c for c in by_path[path] if line < c.start <= line + 15), key=lambda c: c.start,
                         default=None)
        if (target and _distinctive(target.name) and not target.name.startswith("__") and len(target.name) >= 5
                and defined[target.name] == 1 and target.name.lower() not in _GENERIC_NAMES):
            found.setdefault(target.name, target)
    if len(found) < 2:
        return None
    names = sorted(found)[:40]
    homes = sorted({found[n].path for n in names})
    alternation = "|".join(map(re.escape, names))
    defs = r"(?<!def )(?<!func )(?<!fn )(?<!function )(?<!class )"
    check = Forbidden(pattern=rf"{defs}(?<![\w$])(?:{alternation})\s*\(", label="calls to the deprecated "
                      + ", ".join(names[:8]) + (f" and {len(names) - 8} more" if len(names) > 8 else ""),
                      scope=Paths(roles=("source",), languages=(lang,), exclude=tuple(homes)))
    rows = _symbols(snap, [found[n] for n in names])
    body = (f"{len(names)} {lang} functions and classes are deprecated: " + ", ".join(names[:12])
            + (" ..." if len(names) > 12 else "") + ". New source code outside their own files does not call them.")
    evidence = [e for n in names[:2] if (e := snap.evidence_at(found[n], found[n].name))]
    evidence.append(tally_evidence(f"deprecated {lang} definitions (each row is its definition line)", len(names),
                                   [("deprecated definitions", len(names), rows)]))
    return Candidate(key=f"deprecation/{lang}/calls", kind="convention", title=f"Deprecated {lang} API",
                     body=body, evidence=evidence, support=len(names), confidence=1.0, source="code",
                     scope={"languages": [lang]}, eligible=len(names) >= 2, check=check.to_json())


# ── tests, changelog, commits, tooling ─────────────────────────────────

_test_pattern = test_pattern


def mine_tests(snap: Snapshot) -> list[Candidate]:
    from ..codeintel.languages import detect_language
    from ..codeintel.retrieval import _EXAMPLE_PATH_RE

    tests = sorted(p for p in snap.files if path_role(p) == "test" and detect_language(p)
                   and not _EXAMPLE_PATH_RE.search(p))
    if len(tests) < 5:
        return []
    patterns = Counter(_test_pattern(p) for p in tests)
    top = [(pat, n) for pat, n in _top(patterns, 4) if n >= 3]
    if not top:
        return []
    body = "Tests live in " + "; ".join(f"{pat} ({n} files)" for pat, n in top) + f" ({len(tests)} test files)."
    shown = {pat for pat, _ in top}
    others = [p for p in tests if _test_pattern(p) not in shown]
    groups = [(pat, n, [{"path": p} for p in tests if _test_pattern(p) == pat]) for pat, n in top]
    groups.append(("other test files", len(others), [{"path": p} for p in others]))
    py_tests = [c for c in snap.chunks if c.role == "test" and c.language == "python" and c.name.startswith("test")
                and c.kind in ("function", "method")]
    if len(py_tests) >= 20:
        functions = [c for c in py_tests if c.kind == "function"]
        body += (f" Python tests are {'module-level pytest functions' if len(functions) * 2 >= len(py_tests) else 'methods on test classes'}"
                 f" ({len(functions)} of {len(py_tests)} are module-level).")
        groups.append(_minority(snap, (f"module-level test functions, of all {len(py_tests)} tests", functions),
                                (f"test methods on classes, of all {len(py_tests)} tests",
                                 [c for c in py_tests if c.kind != "function"])))
    examples = [next(p for p in tests if _test_pattern(p) == pat) for pat, _ in top]
    evidence = [e for p in examples if (e := file_evidence(snap.checkout, p))]
    evidence.append(tally_evidence(f"test files ({len(tests)})", len(tests), groups))
    share = top[0][1] / len(tests)
    return [Candidate(key="tests/layout", kind="convention", title="Where tests live", body=body, evidence=evidence,
                      support=top[0][1], confidence=share, source="code", eligible=share >= 0.5 and top[0][1] >= 5,
                      check=NewTestFileLocation(patterns=tuple(sorted(shown))).to_json())]


CHANGELOG_RE = re.compile(r"^(CHANGES|CHANGELOG|HISTORY|NEWS|RELEASE-NOTES|RELEASES)(\.\w+)?$", re.I)


def _is_source_path(path: str) -> bool:
    from ..codeintel.languages import detect_language

    spec = detect_language(path)
    return bool(spec and spec.parser) and path_role(path) == "source"


def mine_changelog(snap: Snapshot) -> list[Candidate]:
    logs = sorted(p for p in snap.files if "/" not in p and CHANGELOG_RE.match(p))
    if not logs or not snap.history:
        return []
    source_commits = [c for c in snap.history if c.files and any(_is_source_path(p) for _, p in c.files)][:100]
    if len(source_commits) < 10:
        return []
    best = None
    for log in logs:
        hits = [c for c in source_commits if any(p == log or snap.canonical(p) == log for _, p in c.files)]
        if best is None or len(hits) > len(best[1]):
            best = (log, hits)
    log, hits = best
    share = len(hits) / len(source_commits)
    if share < 0.15:
        return []
    word = "usually" if share >= 0.6 else "often" if share >= 0.3 else "sometimes"
    body = (f"Changes to source code {word} add an entry to {log}: {len(hits)} of the last {len(source_commits)} "
            f"commits that touch source ({_pct(len(hits), len(source_commits))}).")
    head = snap.lines(log)[:80]
    heading = next((line.strip() for line in head if re.match(r"^(#{1,3} |Version |\d+\.\d+)", line.strip())), None)
    if heading:
        body += f" Sections are headed like '{heading[:60]}'."
    text = "\n".join(head)
    refs = {"{issue}`N`/{pr}`N`": text.count("{issue}`") + text.count("{pr}`"),
            ":issue:`N`/:pr:`N`": text.count(":issue:`") + text.count(":pr:`"),
            "#N": len(re.findall(r"(?<![\w{`])#\d+", text))}
    ref, n = max(refs.items(), key=lambda kv: kv[1])
    if n >= 3:
        body += f" Entries cite {ref}."
    renamed = [(c, old) for c in snap.history for old, new in c.renames if new == log]
    if renamed:
        c, old = renamed[0]
        body += f" It was renamed from {old} in {c.sha[:10]} ({c.date[:10]})."
    evidence = [e for e in [file_evidence(snap.checkout, log)] if e]
    evidence += [commit_evidence(c.sha, c.date, c.subject) for c in hits[:3]]
    evidence.append(_commit_tally(snap, f"the last {len(source_commits)} commits that touch source", source_commits,
                                  [log]))
    return [Candidate(key="changelog/entries", kind="convention", title=f"Changelog: {log}", body=body,
                      evidence=evidence, support=len(hits), confidence=share, source="history",
                      eligible=len(hits) >= 10,
                      check=Companion(when=Paths(roles=("source",)), then=Paths(globs=(log,)),
                                      max_files=60).to_json())]


_CONVENTIONAL_RE = re.compile(r"^(feat|fix|docs|chore|refactor|perf|test|tests|build|ci|style)(\([^)]*\))?!?: ")
_AREA_RE = re.compile(r"^[\w./+*-]+(?:[ ,/][\w./+*-]+)?: \S")
_TRAILERS = ("Closes", "Fixes", "Reported-by", "Signed-off-by", "Co-authored-by", "Assisted-by", "Follow-up to",
             "Ref")


def mine_commits(snap: Snapshot) -> list[Candidate]:
    """How commit messages are written: one checkable item per shape that at least 30 % of the latest
    non-merge commits share (a trailer: 20 %), counted with a tally of the commits that do not fit."""
    try:
        messages = commit_messages(snap.mirror, snap.commit, 500)
    except HistoryError:
        return []
    if len(messages) < 50:
        return []
    n = len(messages)
    by_sha = {c.sha: c for c in snap.history[:2 * n + 100]}
    subjects = [m.strip().splitlines()[0] if m.strip() else "" for _, m in messages]
    shapes = [
        ("conventional", "Conventional Commits subjects", 0.3,
         Message(label="start with a Conventional Commits type ('fix: ...', 'feat(scope): ...')",
                 subject=_CONVENTIONAL_RE.pattern)),
        ("area", "'area: change' subjects", 0.3,
         Message(label="start with the area they change ('area: change')", subject=_AREA_RE.pattern)),
        ("pr-number", "subjects ending with the pull-request number", 0.3,
         Message(label="end the subject with the pull-request number '(#N)'", subject=r"\(#\d+\)$")),
    ] + [(f"trailer/{t.lower().replace(' ', '-')}", f"a '{t}:' trailer", 0.2,
          Message(label=f"carry a '{t}:' trailer", trailer=t)) for t in _TRAILERS]
    out: list[Candidate] = []
    for name, title, floor, check in shapes:
        if name == "area" and any(c.key == "commits/conventional" for c in out):
            continue  # a Conventional Commits subject is also an 'area: change' one
        fits = [check.holds(Change(files=[], message=m)) for _, m in messages]
        k = sum(fits)
        if k / n < floor:
            continue
        misses = [by_sha[sha] for (sha, _), ok in zip(messages, fits, strict=True) if not ok and sha in by_sha]
        hits = [by_sha[sha] for (sha, _), ok in zip(messages, fits, strict=True) if ok and sha in by_sha]
        example = next((subjects[i] for i, ok in enumerate(fits) if ok), "")
        body = (f"Commit messages {check.label}: {k} of the last {n} non-merge commits "
                f"({_pct(k, n)}); e.g. '{example[:70]}'.")
        rows = [{"sha": c.sha[:12], "date": c.date[:10], "subject": c.subject[:80], "paths": []} for c in misses]
        evidence = [commit_evidence(c.sha, c.date, c.subject) for c in hits[:MAX_EXAMPLES]]
        evidence.append(tally_evidence(f"the last {n} non-merge commits", n,
                                       [("commits whose message does not fit", n - k, rows)]))
        out.append(Candidate(key=f"commits/{name}", kind="convention", title=f"Commit messages: {title}",
                             body=body, evidence=evidence, support=k, confidence=k / n, source="history",
                             eligible=k / n >= 0.5, check=check.to_json()))
    if not out:
        chosen = snap.history[:MAX_EXAMPLES]
        out.append(Candidate(
            key="commits/style", kind="convention", title="Commit message style",
            body=f"Commit messages (last {n} non-merge commits) share no common prefix or trailer; "
                 f"e.g. '{subjects[0][:60]}'.",
            evidence=[commit_evidence(c.sha, c.date, c.subject) for c in chosen], support=n, confidence=0.0,
            source="history", eligible=False))
    return out


def _toml_value(text: str, section: str, key: str) -> str | None:
    m = re.search(rf"^\[{re.escape(section)}\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if not m:
        return None
    v = re.search(rf"^{re.escape(key)}\s*=\s*(.+)$", m.group(1), re.M)
    return v.group(1).strip() if v else None


def mine_tooling(snap: Snapshot) -> list[Candidate]:
    found: list[str] = []
    evidence: list[dict] = []
    rows: list[dict] = []  # the line behind each fact, or the file when the fact is that it exists

    def cite(path: str, needle: str | re.Pattern | None = None) -> None:
        if needle is None:
            rows.append({"path": path})
            return
        for i, line in enumerate(snap.lines(path), start=1):
            m = needle.search(line) if isinstance(needle, re.Pattern) else (needle if needle in line else None)
            if m:
                rows.append({"path": path, "line": i, "name": m if isinstance(m, str) else m.group(0)})
                return

    if "pyproject.toml" in snap.files:
        text = "\n".join(snap.lines("pyproject.toml"))
        tools = [t for t in ("ruff", "black", "isort", "mypy", "pyright", "pytest", "coverage", "flake8")
                 if re.search(rf"^\[tool\.{t}(\.|\])", text, re.M)]
        if tools:
            found.append("pyproject configures " + ", ".join(tools))
            for t in tools:
                cite("pyproject.toml", f"[tool.{t}")
            length = _toml_value(text, "tool.ruff", "line-length") or _toml_value(text, "tool.black", "line-length")
            if length:
                found.append(f"line length {length}")
                cite("pyproject.toml", "line-length")
    if ".pre-commit-config.yaml" in snap.files:
        hooks = re.findall(r"-\s+id:\s*([\w.-]+)", "\n".join(snap.lines(".pre-commit-config.yaml")))
        if hooks:
            found.append("pre-commit hooks: " + ", ".join(dict.fromkeys(hooks)))
            for hook in dict.fromkeys(hooks):
                cite(".pre-commit-config.yaml", re.compile(rf"id:\s*{re.escape(hook)}(?![\w.-])"))
    if "tox.ini" in snap.files:
        env = re.search(r"^envlist\s*=\s*(.+(?:\n\s+.+)*)", "\n".join(snap.lines("tox.ini")), re.M)
        found.append("tox" + (f" (envs: {' '.join(env.group(1).split())[:80]})" if env else ""))
        cite("tox.ini", "envlist" if env else None)
    for name in (".golangci.yml", ".golangci.yaml"):
        if name in snap.files:
            found.append("golangci-lint (" + name + ")")
            cite(name)
    if "package.json" in snap.files:
        try:
            pkg = json.loads("\n".join(snap.lines("package.json")))
        except ValueError:
            pkg = {}
        scripts = pkg.get("scripts") or {}
        if scripts:
            found.append("npm scripts: " + ", ".join(f"{k}: `{v}`" for k, v in list(scripts.items())[:4])[:300])
            for k in list(scripts)[:4]:
                cite("package.json", f'"{k}"')
    if "Makefile" in snap.files:
        targets = [t for t in re.findall(r"^([a-z][\w-]*):", "\n".join(snap.lines("Makefile")), re.M)
                   if t in ("all", "fmt", "format", "lint", "test", "check", "checksrc")]
        if targets:
            found.append("Makefile targets: " + ", ".join(dict.fromkeys(targets)))
            for t in dict.fromkeys(targets):
                cite("Makefile", f"{t}:")
    if ".editorconfig" in snap.files:
        width = re.search(r"max_line_length\s*=\s*(\d+)", "\n".join(snap.lines(".editorconfig")))
        if width:
            found.append(f".editorconfig max_line_length {width.group(1)}")
            cite(".editorconfig", "max_line_length")
    if ".clang-format" in snap.files:
        width = re.search(r"ColumnLimit:\s*(\d+)", "\n".join(snap.lines(".clang-format")))
        found.append(".clang-format" + (f" (ColumnLimit {width.group(1)})" if width else ""))
        cite(".clang-format", "ColumnLimit" if width else None)
    if "scripts/checksrc.pl" in snap.files:
        found.append("scripts/checksrc.pl checks source style")
        cite("scripts/checksrc.pl")
    if rows:
        evidence.append(tally_evidence("tooling configuration", len(rows),
                                       [("the line (or file) behind each fact", len(rows), rows)]))
    style_docs = sorted(p for p in snap.files if re.search(r"(CODE_STYLE|CODING_STYLE|STYLE|CONTRIBUTING)\.(md|rst)$",
                                                           p, re.I) and path_role(p) in ("docs", "source"))
    for path in style_docs[:4]:
        for i, line in enumerate(snap.lines(path), start=1):
            m = re.search(r"\b(?:never be wider than|wider than|maximum of|at most|limit(?:ed)? to) (\d{2,3}) "
                          r"(columns|characters)", line, re.I)
            if m:
                found.append(f"{path}: source lines at most {m.group(1)} {m.group(2)}")
                if (e := code_evidence(snap.checkout, path, i, i)):
                    evidence.append(e)
                break
    if not found:
        return []
    return [Candidate(key="tooling/summary", kind="fact", title="Formatting, lint and test tooling",
                      body="Tooling: " + "; ".join(found) + ".", evidence=evidence,
                      support=len(rows) + sum(e["kind"] == "code" for e in evidence), confidence=1.0, source="code",
                      eligible=bool(evidence))]


# ── history: co-change, dependencies, moves, origins ───────────────────

def _touching(snap: Snapshot, max_files: int, per_file: int) -> dict[str, list[Commit]]:
    """Each source file's latest commits of at most ``max_files`` files, newest first."""
    touching: dict[str, list[Commit]] = defaultdict(list)
    for c in snap.history:
        if not c.files or len(c.files) > max_files:
            continue
        for _, p in c.files:
            p = snap.canonical(p)
            if p in snap.files and _is_source_path(p) and len(touching[p]) < per_file:
                touching[p].append(c)
    return touching


def mine_cochange(snap: Snapshot, *, max_items: int = 300, per_file: int = WINDOW) -> list[Candidate]:
    out = []
    for path, commits in sorted(_touching(snap, 30, per_file).items(), key=lambda kv: -len(kv[1]))[:max_items]:
        if len(commits) < 8:
            continue
        partners = Counter()
        for c in commits:
            partners.update({snap.canonical(p) for _, p in c.files} - {path})
        top = [(p, n) for p, n in _top(partners, 12) if p in snap.files and n >= 4 and n / len(commits) >= 0.2]
        if not top:
            continue
        top = top[:6]
        body = (f"Files that change with {path} in the same commit (share of its last {len(commits)} commits): "
                + ", ".join(f"{p} {_pct(n, len(commits))}" for p, n in top) + ".")
        lead = top[0][0]
        together = [c for c in commits if lead in {snap.canonical(p) for _, p in c.files}][:2]
        evidence = [e for e in [file_evidence(snap.checkout, path)] if e]
        evidence += [commit_evidence(c.sha, c.date, c.subject) for c in together]
        evidence.append(_commit_tally(snap, f"the last {len(commits)} commits that changed {path}", commits,
                                      [p for p, _ in top]))
        out.append(Candidate(key=f"cochange/{path}", kind="co_change", title=f"Changes with {path}", body=body,
                             evidence=evidence, support=top[0][1], confidence=top[0][1] / len(commits),
                             source="history", scope={"paths": [path]}, eligible=top[0][1] >= 5,
                             check=Companion(when=Paths(globs=(path,)), then=Paths(globs=(lead,)),
                                             max_files=30).to_json()))
    return out


# Test files proper, not their support code: a test home rule asks which test file a change extends.
TESTS_PROPER = Paths(roles=("test",), exclude=("**/conftest.py", "**/fixtures/**", "**/fixture/**", "**/helpers/**",
                                                "**/helper/**", "**/testdata/**", "**/__snapshots__/**"))

_GENERIC_NAMES = {"close", "write", "flush", "parse", "value", "values", "items", "update", "start", "reset", "setup",
                  "string", "format", "result", "check", "build", "error", "name", "main", "init", "test", "tests"}


def _distinctive(name: str) -> bool:
    """Not a plain word: several parts (``has_level_handler``, ``replaceOption``) or a capitalised type name."""
    core = name.strip("_")
    return "_" in core or core[:1].isupper() or any(ch.isupper() for ch in core[1:])


def _code_names(chunks: list[Chunk], defined_in: dict[str, set[str]]) -> list[str]:
    """Names a test would use to exercise this code: distinctive, and defined in this source file only."""
    return sorted({c.name for c in chunks if c.kind in ("function", "method", "class", "macro") and len(c.name) >= 5
                   and not c.name.startswith("__") and c.name.lower() not in _GENERIC_NAMES
                   and _distinctive(c.name) and len(defined_in[c.name]) == 1})


def mine_test_homes(snap: Snapshot, *, max_items: int = 300, per_file: int = WINDOW) -> list[Candidate]:
    """The existing test files that a source file's tests live in, so a change extends them
    instead of starting a new test file.

    A test file counts for a source file when it changed in at least 3 (and 15 %) of the source file's
    latest focused commits (at most ``FOCUSED`` files, so repository-wide sweeps do not count), and at
    the learned commit it uses the source file's code (a function or class name defined in no other source
    file).
    The evidence is that line and every counted commit."""
    by_path: dict[str, list[Chunk]] = defaultdict(list)
    defined_in: dict[str, set[str]] = defaultdict(set)
    for c in snap.source():
        by_path[c.path].append(c)
        defined_in[c.name].add(c.path)
    out = []
    for path, commits in sorted(_touching(snap, FOCUSED, per_file).items(), key=lambda kv: -len(kv[1]))[:max_items]:
        names = _code_names(by_path.get(path, []), defined_in)
        if not names:
            continue
        uses = re.compile(r"(?<![\w$])(" + "|".join(map(re.escape, names[:300])) + r")(?![\w$])")
        tests = Counter()
        for c in commits:
            tests.update({q for _, p in c.files if (q := snap.canonical(p)) in snap.files and path_role(q) == "test"
                          and not TEST_SUPPORT_RE.search(q)})
        top = []
        for test, n in _top(tests, 6):
            if n < 3 or n / len(commits) < 0.15:
                break
            hit = next(((i, m.group(1)) for i, line in enumerate(snap.lines(test), start=1)
                        if (m := uses.search(line))), None)
            if hit:
                top.append((test, n, *hit))
            if len(top) == 3:
                break
        if not top:
            continue
        body = (f"Existing tests that use {path}'s code: "
                + ", ".join(f"{t} (uses {name}; in the same commit in {n} of {path}'s last {len(commits)} commits "
                            f"of at most {FOCUSED} files)" for t, n, _, name in top) + ".")
        evidence = [e for t, _, line, _ in top[:2] if (e := code_evidence(snap.checkout, t, line, line))]
        evidence.append(_commit_tally(snap, f"the last {len(commits)} commits of at most {FOCUSED} files that changed "
                                            f"{path}", commits, [t for t, *_ in top]))
        out.append(Candidate(key=f"testhome/{path}", kind="co_change", title=f"Tests for {path}", body=body,
                             evidence=evidence, support=top[0][1], confidence=top[0][1] / len(commits),
                             source="history", scope={"paths": [path]}, eligible=top[0][1] >= 4,
                             check=Companion(when=Paths(globs=(path,)), then=Paths(globs=tuple(sorted(t for t, *_ in top))),
                                             given=TESTS_PROPER).to_json()))
    return out


def _requirement_names(block: str) -> set[str]:
    """Package names of the quoted requirement strings in ``block`` (markers such as
    ``python_version < '3.10'`` sit inside the outer quotes and are not names)."""
    names = set()
    for double, single in re.findall(r'"([^"]*)"|\'([^\']*)\'', block):
        m = re.match(r"\s*([A-Za-z][\w.-]*)", double or single)
        if m:
            names.add(m.group(1).lower())
    return names


def _deps_python(text: str) -> tuple[set[str], str | None]:
    deps: set[str] = set()
    m = re.search(r"^dependencies\s*=\s*\[(.*?)^\]", text, re.M | re.S)
    if m:
        deps |= _requirement_names(m.group(1))
    m = re.search(r"install_requires\s*=\s*\[(.*?)\]", text, re.S)
    if m:
        deps |= _requirement_names(m.group(1))
    py = re.search(r"""(?:requires-python|python_requires)\s*=\s*["']([^"']+)""", text)
    return deps, py.group(1) if py else None


def _deps_go(text: str) -> tuple[set[str], str | None]:
    deps = set(re.findall(r"^\s*(?:require\s+)?([\w.-]+\.[a-z]{2,}/[\w./-]+)\s+v[\d.]+(?!.*// indirect)", text, re.M))
    go = re.search(r"^go\s+([\d.]+)", text, re.M)
    return deps, go.group(1) if go else None


def _deps_npm(text: str) -> tuple[set[str], str | None]:
    try:
        pkg = json.loads(text)
    except ValueError:
        return set(), None
    deps = set((pkg.get("dependencies") or {}) | (pkg.get("peerDependencies") or {}))
    return deps, (pkg.get("engines") or {}).get("node")


def _author_commit(mirror: Path, before: str, version: tuple, manifest: str) -> tuple:
    """A mainline merge brought the change: credit the merged branch's latest commit to the manifest."""
    sha = version[0]
    try:
        out = _git(mirror, "log", "-1", "--no-merges", "--format=%H%x00%cI%x00%s", f"{before}..{sha}", "--",
                   manifest).strip()
    except HistoryError:
        return version
    if not out or out.split("\x00", 1)[0] == sha:
        return version
    real, date, subject = out.split("\x00", 2)
    return (real, date, subject, *version[3:])


def _diff_lines(mirror: Path, shas: list[str], manifest: str, pattern: re.Pattern) -> tuple | None:
    """(sha, removed, added): the manifest lines matching ``pattern`` that the first of ``shas`` to touch
    them removed and added, or None."""
    for sha in shas:
        try:
            diff = _git(mirror, "show", "-M", "--diff-merges=first-parent", "--format=", sha, "--",
                        manifest).splitlines()
        except HistoryError:
            continue
        removed = [line[1:] for line in diff if line.startswith("-") and not line.startswith("---")
                   and pattern.search(line[1:])]
        added = [line[1:] for line in diff if line.startswith("+") and not line.startswith("+++")
                 and pattern.search(line[1:])]
        if removed or added:
            return sha, removed[:3], added[:3]
    return None


_RUNTIME_LINE = {"Python": re.compile(r"requires-python|python_requires"), "Go": re.compile(r"^go\s+\d"),
                 "Node.js": re.compile(r'"node"\s*:')}
_DEPS_START = {"pyproject.toml": re.compile(r"^dependencies\s*=\s*\["), "setup.py": re.compile(r"install_requires"),
               "go.mod": re.compile(r"^require\s*\("), "package.json": re.compile(r'^\s*"dependencies"\s*:')}


def _deps_block(snap: Snapshot, manifest: str) -> dict | None:
    """Code evidence for the dependency list in ``manifest`` at the learned commit (up to 60 lines)."""
    lines = snap.lines(manifest)
    start = next((i for i, line in enumerate(lines, start=1) if _DEPS_START[manifest].search(line)), None)
    if start is None:
        return None
    end = next((i for i in range(start, min(len(lines), start + 60) + 1)
                if re.match(r"^\s*[\])}]", lines[i - 1]) and i > start), min(len(lines), start + 60))
    return code_evidence(snap.checkout, manifest, start, end)


_MANIFESTS: dict[str, tuple[Callable[[str], tuple[set[str], str | None]], str]] = {
    "pyproject.toml": (_deps_python, "Python"), "setup.py": (_deps_python, "Python"),
    "go.mod": (_deps_go, "Go"), "package.json": (_deps_npm, "Node.js"),
}


_IMPORT_LINE = {
    "python": r"^\s*(?:import|from)\s+[\w.]+",
    "go": r'^\s*(?:import\s+)?(?:[\w.]+\s+)?"[^"\s]+"\s*$',
    "javascript": r"""^\s*import\b|\brequire\(\s*['"]|\bimport\(\s*['"]""",
}
_IMPORT_LINE["typescript"] = _IMPORT_LINE["javascript"]
_MANIFEST_LANGUAGES = {"pyproject.toml": ("python",), "setup.py": ("python",), "go.mod": ("go",),
                       "package.json": ("javascript", "typescript")}


def _import_of(language: str, dep: str) -> str | None:
    """A regex for an import of package ``dep`` on one line, or None when its import name is not its own."""
    if language == "python":
        name = dep.lower().replace("-", "_")
        if not name.isidentifier():
            return None
        return rf"^\s*(?:import\s+{re.escape(name)}\b|from\s+{re.escape(name)}(?:\.[\w.]+)?\s+import\b)"
    if language == "go":
        return rf'"{re.escape(dep)}(?:/[^"]*)?"'
    return rf"""(?:\bfrom\s+|\brequire\(\s*|\bimport\(\s*|^\s*import\s+)['"]{re.escape(dep)}(?:/[^'"]*)?['"]"""


def _no_import(snap: Snapshot, manifest: str, removed: dict[str, tuple]) -> Candidate | None:
    """One rule per manifest: code does not import a package that was dropped from it. It applies to
    changes that add an import line in that language."""
    langs = _MANIFEST_LANGUAGES[manifest]
    deps = sorted(d for d in removed if _import_of(langs[0], d))
    if not deps:
        return None
    pattern = "|".join(f"(?:{_import_of(langs[0], d)})" for d in deps)
    names = ", ".join(deps[:8]) + (f" and {len(deps) - 8} more" if len(deps) > 8 else "")
    check = Forbidden(pattern=pattern, label=f"an import of a dropped dependency ({names})",
                      scope=Paths(roles=("source", "test"), languages=langs), when=_IMPORT_LINE[langs[0]])
    evidence, rows = [], []
    known = {c.sha for c in snap.history}
    for dep in deps:
        (sha, date, subject, *_rest), _main = removed[dep]
        evidence.append(commit_evidence(sha, date, subject))
        if sha in known:  # a mainline merge is cited as a commit, not as a tally row (rows are non-merge)
            rows.append({"sha": sha[:12], "date": date[:10], "subject": subject[:80], "paths": [manifest]})
    body = (f"Packages dropped from {manifest} are not imported again: {names}. "
            f"Each was removed in the commit listed in its evidence and is not a dependency at the indexed commit.")
    return Candidate(key=f"history/no-import/{manifest}", kind="convention", title=f"Dropped dependencies ({manifest})",
                     body=body, evidence=evidence[:MAX_EXAMPLES] + [tally_evidence(
                         f"dependencies dropped from {manifest}", len(deps),
                         [("the commit that dropped each (non-merge commits)", len(rows), rows)])],
                     support=len(deps), confidence=1.0, source="history", scope={"languages": list(langs)},
                     eligible=True, check=check.to_json())


def mine_dependencies(snap: Snapshot) -> list[Candidate]:
    out = []
    for manifest, (parse, runtime) in _MANIFESTS.items():
        if manifest not in snap.files:
            continue
        try:  # the mainline's own sequence of versions; merged branches interleave otherwise
            commits = list(reversed(commits_touching(snap.mirror, snap.commit, [manifest], limit=400,
                                                     first_parent=True)))
        except HistoryError:
            continue
        versions = []
        for sha, date, subject in commits:
            text = file_at(snap.mirror, sha, manifest)
            if text is not None:
                versions.append((sha, date, subject, *parse(text)))
        if len(versions) < 2:
            continue
        current_deps, current_runtime = versions[-1][3], versions[-1][4]
        removed: dict[str, tuple] = {}
        runtime_changes = []
        for prev, cur in zip(versions, versions[1:], strict=False):
            gone = {dep for dep in prev[3] - cur[3] if dep not in current_deps}
            main = cur  # the mainline commit (perhaps a merge) where the manifest changed
            if gone or (prev[4] != cur[4] and cur[4]):
                cur = _author_commit(snap.mirror, prev[0], cur, manifest)
            for dep in gone:
                removed[dep] = (cur, main)
            if prev[4] != cur[4] and cur[4]:
                runtime_changes.append((prev[4], cur, main))
        block = _deps_block(snap, manifest)
        for dep, ((sha, date, subject, *_rest), main) in sorted(removed.items()):
            evidence = [commit_evidence(sha, date, subject)]
            change = _diff_lines(snap.mirror, [sha, main[0]], manifest,
                                 re.compile(rf"(?<![\w.-]){re.escape(dep)}(?![\w-])", re.I))
            if change and change[1]:
                where = (sha, date, subject) if change[0] == sha else main[:3]
                evidence.append(diff_evidence(*where, manifest, removed=change[1]))
            if block:
                evidence.append(block)
            out.append(Candidate(
                key=f"history/dependency-removed/{dep}", kind="history", title=f"{dep} is no longer a dependency",
                body=f"{dep} was removed from {manifest} in {sha[:10]} ({date[:10]}): '{subject}'. It is not a "
                     f"dependency at the indexed commit.",
                evidence=evidence, support=1, confidence=1.0, source="history",
                scope={"paths": [manifest]}, eligible=True))
        if (item := _no_import(snap, manifest, removed)):
            out.append(item)
        if runtime_changes and current_runtime:
            recent = runtime_changes[-3:]
            steps = "; ".join(f"{old or '?'} -> {new[4]} in {new[0][:10]} ({new[1][:10]}, '{new[2][:80]}')"
                              for old, new, _ in reversed(recent))
            evidence = [e for e in [_line_evidence(snap, manifest, 1, len(snap.lines(manifest)),
                                                   _RUNTIME_LINE[runtime])] if e]
            for _, new, main in reversed(recent):
                evidence.append(commit_evidence(new[0], new[1], new[2]))
                if (change := _diff_lines(snap.mirror, [new[0], main[0]], manifest, _RUNTIME_LINE[runtime])):
                    where = new[:3] if change[0] == new[0] else main[:3]
                    evidence.append(diff_evidence(*where, manifest, removed=change[1], added=change[2]))
            out.append(Candidate(
                key=f"history/runtime/{runtime.lower()}", kind="history", title=f"Supported {runtime} versions",
                body=f"{runtime} requirement in {manifest} is {current_runtime}. Recent changes, newest first: {steps}.",
                evidence=evidence, support=len(recent),
                confidence=1.0, source="history", scope={"paths": [manifest]}, eligible=True))
    return out


def mine_moves(snap: Snapshot) -> list[Candidate]:
    out, seen = [], set()
    for c in snap.history:  # newest first: when a directory moved the same way twice, the latest move is kept
        groups: dict[tuple[str, str], int] = Counter()
        moved: dict[tuple[str, str], list[str]] = defaultdict(list)
        for old, new in c.renames:
            o, n = PurePosixPath(old).parts, PurePosixPath(new).parts
            k = 0
            while k < min(len(o), len(n)) and o[len(o) - 1 - k] == n[len(n) - 1 - k]:
                k += 1
            if k == 0 or k == len(o) and k == len(n):
                continue
            group = ("/".join(o[:len(o) - k]) or ".", "/".join(n[:len(n) - k]) or ".")
            groups[group] += 1
            moved[group].append(new)
        for (src, dst), count in groups.items():
            if count < 5 or (src, dst) in seen or (dst != "." and not any(p.startswith(dst + "/") for p in snap.files)):
                continue
            seen.add((src, dst))
            out.append(Candidate(
                key=f"history/move/{src}->{dst}"[:255], kind="history", title=f"{src}/ moved to {dst}/",
                body=f"{count} files moved from {src}/ to {dst}/ in {c.sha[:10]} ({c.date[:10]}): '{c.subject}'.",
                evidence=[commit_evidence(c.sha, c.date, c.subject),
                          tally_evidence(f"files moved from {src}/ to {dst}/", count, [
                              ("moved, under their new names", count,
                               [{"sha": c.sha[:12], "date": c.date[:10], "subject": c.subject[:80],
                                 "paths": sorted(moved[(src, dst)])}])])],
                support=count, confidence=1.0,
                source="history", eligible=True))
    return out


def mine_origins(snap: Snapshot, *, max_items: int = 300) -> list[Candidate]:
    sizes = Counter(c.path for c in snap.source())
    candidates = {p for p, n in sizes.items() if n >= 3}
    origin: dict[str, tuple[Commit, str]] = {}
    for c in snap.history:  # newest first: the last "A" seen is the oldest
        for status, p in c.files:
            now = snap.canonical(p)
            if status == "A" and now in candidates:
                origin[now] = (c, c.recorded(p))
    out = []
    for path, (c, added_as) in sorted(origin.items(), key=lambda kv: -sizes[kv[0]])[:max_items]:
        body = f"{path} was added in {c.sha[:10]} ({c.date[:10]}): '{c.subject}'."
        links = []
        if added_as != path:
            link = snap.name_link(added_as, path)
            if link is None:
                continue  # the renames do not connect; say nothing rather than something unprovable
            hops = "; ".join(f"renamed to {h['to']} in {h['sha'][:10]} ({h['date']})" for h in link["renames"])
            body = f"{path} was added as {added_as} in {c.sha[:10]} ({c.date[:10]}): '{c.subject}'; {hops}."
            links.append(link)
        row = {"sha": c.sha[:12], "date": c.date[:10], "subject": c.subject[:80], "paths": [added_as],
               "added": [added_as]}
        evidence = [commit_evidence(c.sha, c.date, c.subject),
                    tally_evidence(f"how {path} began", 1, [("the commit that added it", 1, [row])], links)]
        out.append(Candidate(
            key=f"history/origin/{path}"[:255], kind="history", title=f"Origin of {path}", body=body,
            evidence=evidence, support=1, confidence=1.0, source="history",
            scope={"paths": [path]}, eligible=True))
    return out


# ── procedural: what changes together when something new is added ──────

def addition_pattern(path: str) -> str:
    p = PurePosixPath(path)
    stem, ext = p.stem, p.suffix
    if (m := re.match(r"^([A-Z][A-Z0-9]*_)", stem)):
        pat = m.group(1) + "*"
    elif re.match(r"^[A-Za-z]+\d+$", stem):
        pat = re.sub(r"\d+$", "N", stem)
    elif stem.startswith("test_"):
        pat = "test_*"
    elif stem.endswith("_test"):
        pat = "*_test"
    else:
        pat = "*"
    parent = str(p.parent)
    return (f"{parent}/" if parent != "." else "") + pat + ext


def _glob(pattern: str) -> str:
    return pattern.replace("N", "*") if re.search(r"[A-Za-z]N(\.|$)", pattern) else pattern


def _additions(snap: Snapshot, recent: int) -> dict[str, list[Commit]]:
    """The latest commits (of at most 30 files) that added a file of each addition pattern."""
    by_pattern: dict[str, list[Commit]] = defaultdict(list)
    for c in snap.history:
        if not c.files or len(c.files) > 30:
            continue
        for pat in {addition_pattern(snap.canonical(p)) for s, p in c.files if s == "A"}:
            if len(by_pattern[pat]) < recent:
                by_pattern[pat].append(c)
    return {pat: commits for pat, commits in by_pattern.items()
            if len(commits) >= 5 and pat != "*" and not pat.endswith("/*")}


def _addition_steps(snap: Snapshot, pat: str, commits: list[Commit]) -> list[tuple[str, str, int, list]]:
    """(target, how, count, rows): the existing files changed (``how`` = "changes") and the other kinds of
    new file added (``how`` = "adds") in at least half of the commits that added a ``pat`` file."""
    changed, added = Counter(), Counter()
    for c in commits:
        changed.update({snap.canonical(p) for s, p in c.files if s == "M"})
        added.update({q for s, p in c.files if s == "A" and (q := addition_pattern(snap.canonical(p))) != pat})
    out = []
    for target, n in _top(changed, 15):
        if target in snap.files and n / len(commits) >= 0.5:
            rows = [{"sha": c.sha[:12], "date": c.date[:10], "subject": c.subject[:80],
                     "paths": sorted({c.recorded(p) for s, p in c.files if s == "M" and snap.canonical(p) == target})}
                    for c in commits]
            out.append((target, "changes", n, rows))
    for target, n in _top(added, 5):
        if n / len(commits) >= 0.5 and target != "*" and not target.endswith("/*"):
            rows = []
            for c in commits:
                new = sorted({c.recorded(p) for s, p in c.files
                              if s == "A" and addition_pattern(snap.canonical(p)) == target})
                rows.append({"sha": c.sha[:12], "date": c.date[:10], "subject": c.subject[:80], "paths": new,
                             "added": new})
            out.append((target, "adds", n, rows))
    return out


def mine_additions(snap: Snapshot, *, recent: int = 40) -> list[Candidate]:
    """Checkable steps of the playbooks: adding a new file of a pattern also changes (or adds) another file."""
    out = []
    for pat, commits in sorted(_additions(snap, recent).items()):
        for target, how, n, rows in _addition_steps(snap, pat, commits):
            what = target if how == "changes" else f"a new {target}"
            body = (f"Of the last {len(commits)} commits (of at most 30 files) that added a new {pat}, {n} also "
                    f"{'changed' if how == 'changes' else 'added'} {what} ({_pct(n, len(commits))}).")
            if how == "changes":
                then = Paths(globs=(target,))
            else:
                then = Paths(globs=(_glob(target),))
            check = NewFileCompanion(new=Paths(globs=(_glob(pat),)), then=then, then_added=how == "adds")
            evidence = [commit_evidence(c.sha, c.date, c.subject) for c in commits[:2]]
            evidence.append(tally_evidence(f"the last {len(commits)} commits that added a new {pat}", len(commits),
                                           [(f"each commit, with the {'changed' if how == 'changes' else 'added'} "
                                             f"{what} when it has one", len(commits), rows)]))
            out.append(Candidate(key=f"addition/{pat}/{how}/{target}"[:255], kind="co_change",
                                 title=f"Adding a {pat}: {how} {target}", body=body, evidence=evidence, support=n,
                                 confidence=n / len(commits), source="history",
                                 scope={"paths": [_glob(pat), _glob(target)]}, eligible=n >= 5,
                                 check=check.to_json()))
    return out


def mine_playbooks(snap: Snapshot, *, recent: int = 40) -> list[SkillCandidate]:
    out = []
    for pat, commits in sorted(_additions(snap, recent).items()):
        changed = Counter()
        for c in commits:
            changed.update({snap.canonical(p) for s, p in c.files if s == "M"})
        steps = [(p, n) for p, n in _top(changed, 15) if p in snap.files and n / len(commits) >= 0.5]
        if len(steps) < 2 or steps[0][1] / len(commits) < 0.6:
            continue
        name = "add-" + re.sub(r"[^a-z0-9]+", "-", pat.lower()).strip("-")[:110]
        rates = ", ".join(f"{p} ({_pct(n, len(commits))})" for p, n in steps[:5])
        description = f"Adding a new {pat} (seen in {len(commits)} recent commits) usually also changes {rates}."
        body = "\n".join([f"# Add a new {pat}", "", f"Learned from the last {len(commits)} commits that added one.",
                          "", "Steps (files that change in the same commit, with how often):"]
                         + [f"{i}. Update {p} ({_pct(n, len(commits))} of those commits)"
                            for i, (p, n) in enumerate(steps, start=1)]
                         + ["", "Example commits:"]
                         + [f"- {c.sha[:10]} ({c.date[:10]}): {c.subject}" for c in commits[:5]])
        resources = {"pattern": pat, "commits": len(commits),
                     "files": [{"path": p, "rate": round(n / len(commits), 3)} for p, n in steps],
                     "examples": [{"sha": c.sha, "date": c.date[:10], "subject": c.subject} for c in commits[:8]]}
        instance = next((p for p in sorted(snap.files) if addition_pattern(p) == pat), None)
        evidence = [commit_evidence(c.sha, c.date, c.subject) for c in commits[:3]]
        if instance and (e := file_evidence(snap.checkout, instance)):
            evidence.append(e)
        out.append(SkillCandidate(
            name=name, title=f"Add a new {pat}", description=description, body=body, resources=resources,
            evidence=evidence, support=len(commits), confidence=steps[0][1] / len(commits), source="history",
            scope={"paths": [_glob(pat)] + [p for p, _ in steps]}, eligible=len(commits) >= 5,
            rules=[f"addition/{pat}/changes/{p}"[:255] for p, _ in steps]))
    return out


MINERS: dict[str, Callable[[Snapshot], list[Candidate]]] = {
    "naming": lambda s: mine_naming(s) + mine_prefixes(s),
    "docs": mine_docs,
    "typing": mine_python_typing,
    "exceptions": mine_exceptions,
    "deprecation": mine_deprecation,
    "tests": mine_tests,
    "changelog": mine_changelog,
    "commits": mine_commits,
    "tooling": mine_tooling,
    "cochange": mine_cochange,
    "testhome": mine_test_homes,
    "addition": mine_additions,
    "history": lambda s: mine_dependencies(s) + mine_moves(s) + mine_origins(s),
}


def run_miners(snap: Snapshot, families: list[str] | None = None, *, on_error=None) -> tuple[list[Candidate], dict]:
    """Every L1 miner (or those in ``families``) on ``snap``: the candidates, each tagged with its family,
    and per family the number found (or why it failed) and its time in seconds. One miner failing never
    blocks the others."""
    import time

    candidates: list[Candidate] = []
    report: dict = {"ran": set(), "by_family": {}, "timings": {}}
    for family, miner in MINERS.items():
        if families and family not in families:
            continue
        t = time.perf_counter()
        try:
            found = miner(snap)
        except (HistoryError, OSError, ValueError) as exc:
            if on_error:
                on_error(family, exc)
            report["by_family"][family] = f"failed: {exc}"[:200]
            continue
        for cand in found:
            cand.family = family
        candidates += found
        report["ran"].add(family)
        report["by_family"][family] = len(found)
        report["timings"][family] = round(time.perf_counter() - t, 2)
    return candidates, report


def tracked_files(checkout: Path) -> set[str]:
    return set(_git(checkout, "ls-files").splitlines())
