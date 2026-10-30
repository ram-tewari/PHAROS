"""Deterministic (L1) miners: repository facts and conventions with support counts.

Every miner reads the existing index (``document_chunks.chunk_metadata``:
path, name, parent, signature, docstring, calls), the working tree at the
indexed commit, or the full git history, so every language is covered the
same way. Rules shared by all of them:

* conventions are measured on **source** files only (``path_role``), never
  averaged with tests, docs or examples;
* every item says how many cases support it, and cites evidence PHAROS can
  re-check (lines with a hash, a file blob, or a commit);
* an item is ``eligible`` to auto-activate only when its own rule holds
  (typically ≥ 90 % agreement over ≥ 20 cases, or an exact git event);
* nothing is called removed or abandoned unless it is absent at the
  indexed commit.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..codeintel.retrieval import path_role
from .history import Commit, HistoryError, _git, commit_messages, commits_touching, file_at
from .memory import Candidate, SkillCandidate, code_evidence, commit_evidence, file_evidence

MIN_CASES = 20
STRONG = 0.9
MAX_EXAMPLES = 4


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


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "0%"


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

def case_style(name: str) -> str | None:
    core = name.strip("_")
    if not core or not re.search(r"[A-Za-z]", core):
        return None
    if "_" in core:
        if core.upper() == core:
            return "UPPER_SNAKE"
        if core.lower() == core:
            return "snake_case"
        return "Prefixed_snake"
    if core.lower() == core:
        return None  # one lower-case word fits snake_case and camelCase alike
    if core.upper() == core:
        return None
    return "PascalCase" if core[0].isupper() else "camelCase"


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
        if lang == "go" and kind != "macro":
            mixed = counts["camelCase"] + counts["PascalCase"]
            exported = sum(1 for c in chunks if c.name[:1].isupper())
            body = (f"Go {_KIND_WORDS[kind]} use MixedCaps, never underscores: {mixed} of {len(styled)} multi-part "
                    f"names ({_pct(mixed, len(styled))}). Exported names start upper-case "
                    f"({exported} of {len(chunks)} {_KIND_WORDS[kind]} are exported).")
            top, n = "MixedCaps", mixed
        else:
            top, n = counts.most_common(1)[0]
            body = (f"{lang.capitalize()} {_KIND_WORDS[kind]} in source files are {top}: {n} of {len(styled)} "
                    f"multi-part names ({_pct(n, len(styled))}).")
            if lang == "python":
                private = sum(1 for c in chunks if c.name.startswith("_") and not c.name.startswith("__"))
                body += f" Private helpers start with an underscore ({private} of {len(chunks)})."
        share = n / len(styled)
        examples = [c for c, s in styled if s == top or (top == "MixedCaps" and s in ("camelCase", "PascalCase"))]
        evidence = [e for c in _spread(examples) if (e := snap.evidence_at(c, c.name))]
        out.append(Candidate(
            key=f"naming/{lang}/{kind}", kind="convention", title=f"{lang} {_KIND_WORDS[kind]}: {top}",
            body=body + " Examples: " + ", ".join(c.name for c in _spread(examples)) + ".",
            evidence=evidence, support=n, confidence=share, source="code",
            scope={"languages": [lang]}, eligible=share >= STRONG))
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
        evidence_from = documented
        if lang == "python":
            styles = {
                "reST field lists (:param x:)": sum(":param" in c.docstring or ":return" in c.docstring
                                                    for c in documented),
                "Google style (Args:/Returns:)": sum("Args:" in c.docstring or "Returns:" in c.docstring
                                                     for c in documented),
                "NumPy style (Parameters ----)": sum("Parameters --" in c.docstring for c in documented),
            }
            style, n = max(styles.items(), key=lambda kv: kv[1])
            if n >= 10:
                body += f" Docstrings use {style} ({n})."
            directives = Counter(m for c in documented for m in _DIRECTIVE_RE.findall(c.docstring))
            if sum(directives.values()) >= 5:
                body += (" API history is recorded in docstrings with Sphinx directives: "
                         + ", ".join(f".. {d}:: ({n})" for d, n in directives.most_common()) + ".")
                evidence_from = [c for c in documented if _DIRECTIVE_RE.search(c.docstring)]
        elif lang == "go":
            named = sum(c.docstring.startswith(c.name) for c in documented)
            body += f" Doc comments start with the symbol's name ({named} of {len(documented)})."
        evidence = [e for c in _spread(evidence_from) if (e := snap.evidence_at(c, c.name, span=3))]
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
        out.append(Candidate(key="typing/python/annotations", kind="convention", title="Python type hints",
                             body=body, evidence=evidence, support=returns, confidence=share, source="code",
                             scope={"languages": ["python"]}, eligible=share >= STRONG))
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
            out.append(Candidate(
                key="typing/python/future-annotations", kind="convention",
                title="from __future__ import annotations",
                body=(f"Python source modules start with `from __future__ import annotations`: {len(with_future)} "
                      f"of {len(modules)} ({_pct(len(with_future), len(modules))})."),
                evidence=evidence, support=len(with_future), confidence=share, source="code",
                scope={"languages": ["python"]}, eligible=share >= STRONG and len(with_future) >= 5))
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
        roots = [(name, n) for name, n in children.most_common() if n >= 3]
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
        body = (f"Errors are raised as subclasses of {root} (defined in {by_name[root].path}, base "
                f"{', '.join(bases[root]) or '-'}), not bare built-in errors: {len(descendants) - 1} of the "
                f"{len(exc)} {lang} exception classes derive from it ({k} of them live in {home}/).")
        if roots[1:4]:
            body += " Other bases: " + ", ".join(f"{name} ({k})" for name, k in roots[1:4]) + "."
        ev_chunks = [by_name[root]] + _spread([by_name[x] for x in descendants if x != root], 3)
        evidence = [e for c in ev_chunks if (e := snap.evidence_at(c, c.name))]
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
                level, n = levels.most_common(1)[0]
                call = f"warnings.warn(..., DeprecationWarning, stacklevel={level})"
                counts += f"; stacklevel={level} in {n}"
            body = f"Deprecations warn at runtime with `{call}` ({counts})."
            if removals:
                phrase, n = removals.most_common(1)[0]
                body += f" Messages say the old name 'will be removed in {phrase}' ({n} of {len(sites)})."
            evidence = [e for path, line in sites[:: max(1, len(sites) // MAX_EXAMPLES)][:MAX_EXAMPLES]
                        if (e := code_evidence(snap.checkout, path, line, min(line + 4, len(snap.lines(path)))))]
            out.append(Candidate(key="deprecation/python", kind="convention", title="How Python APIs are deprecated",
                                 body=body, evidence=evidence, support=len(sites),
                                 confidence=max(levels.values(), default=len(sites)) / len(sites), source="code",
                                 scope={"languages": ["python"]}, eligible=len(sites) >= 5))
    marks = {"go": ("// Deprecated:", "Doc comments mark deprecated Go API with a `// Deprecated:` paragraph"),
             "typescript": ("@deprecated", "Deprecated TypeScript API is marked with a `@deprecated` JSDoc tag"),
             "javascript": ("@deprecated", "Deprecated JavaScript API is marked with a `@deprecated` JSDoc tag"),
             "rust": ("#[deprecated", "Deprecated Rust items carry `#[deprecated(...)]`")}
    for lang, (needle, sentence) in marks.items():
        sites = [(p, i) for p in by_lang.get(lang, []) for i, line in enumerate(snap.lines(p), start=1)
                 if needle in line]
        if len(sites) >= 3:
            evidence = [e for p, i in sites[:MAX_EXAMPLES] if (e := code_evidence(snap.checkout, p, i, i))]
            out.append(Candidate(key=f"deprecation/{lang}", kind="convention", title=f"How {lang} APIs are deprecated",
                                 body=f"{sentence} ({len(sites)} sites).", evidence=evidence, support=len(sites),
                                 confidence=1.0, source="code", scope={"languages": [lang]},
                                 eligible=len(sites) >= 5))
    return out


# ── tests, changelog, commits, tooling ─────────────────────────────────

def _test_pattern(path: str) -> str:
    p = PurePosixPath(path)
    name = p.name
    for regex, repl in ((r"^test_.+\.py$", "test_*.py"), (r".+_test\.go$", "*_test.go"),
                        (r".+\.(test|spec)\.([jt]sx?)$", r"*.\1.\2"), (r"^[A-Za-z]+\d+(\.\w+)?$", None)):
        if re.match(regex, name):
            name = re.sub(r"\d+", "N", name) if repl is None else re.sub(regex, repl, name)
            break
    else:
        name = "*" + p.suffix
    parent = re.sub(r"\d+", "N", str(p.parent))
    return f"{parent}/{name}" if parent != "." else name


def mine_tests(snap: Snapshot) -> list[Candidate]:
    from ..codeintel.languages import detect_language
    from ..codeintel.retrieval import _EXAMPLE_PATH_RE

    tests = sorted(p for p in snap.files if path_role(p) == "test" and detect_language(p)
                   and not _EXAMPLE_PATH_RE.search(p))
    if len(tests) < 5:
        return []
    patterns = Counter(_test_pattern(p) for p in tests)
    top = [(pat, n) for pat, n in patterns.most_common(4) if n >= 3]
    if not top:
        return []
    body = "Tests live in " + "; ".join(f"{pat} ({n} files)" for pat, n in top) + f" ({len(tests)} test files)."
    py_tests = [c for c in snap.chunks if c.role == "test" and c.language == "python" and c.name.startswith("test")
                and c.kind in ("function", "method")]
    if len(py_tests) >= 20:
        module_level = sum(c.kind == "function" for c in py_tests)
        body += (f" Python tests are {'module-level pytest functions' if module_level * 2 >= len(py_tests) else 'methods on test classes'}"
                 f" ({module_level} of {len(py_tests)} are module-level).")
    examples = [p for pat, _ in top[:2] for p in tests if _test_pattern(p) == pat][:MAX_EXAMPLES]
    evidence = [e for p in examples if (e := file_evidence(snap.checkout, p))]
    share = top[0][1] / len(tests)
    return [Candidate(key="tests/layout", kind="convention", title="Where tests live", body=body, evidence=evidence,
                      support=top[0][1], confidence=share, source="code", eligible=share >= 0.5 and top[0][1] >= 5)]


CHANGELOG_RE = re.compile(r"^(CHANGES|CHANGELOG|HISTORY|NEWS|RELEASE-NOTES|RELEASES)(\.\w+)?$", re.I)


def _is_source_path(path: str) -> bool:
    from ..codeintel.languages import detect_language

    spec = detect_language(path)
    return bool(spec and spec.parser) and path_role(path) == "source"


def mine_changelog(snap: Snapshot) -> list[Candidate]:
    logs = sorted(p for p in snap.files if "/" not in p and CHANGELOG_RE.match(p))
    if not logs or not snap.history:
        return []
    source_commits = [c for c in snap.history if c.files and any(_is_source_path(p) for _, p in c.files)][:300]
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
    return [Candidate(key="changelog/entries", kind="convention", title=f"Changelog: {log}", body=body,
                      evidence=evidence, support=len(hits), confidence=share, source="history",
                      eligible=len(hits) >= 10)]


_CONVENTIONAL_RE = re.compile(r"^(feat|fix|docs|chore|refactor|perf|test|tests|build|ci|style)(\([^)]*\))?!?: ")
_AREA_RE = re.compile(r"^[\w./+*-]+(?:[ ,/][\w./+*-]+)?: \S")
_TRAILERS = ("Closes", "Fixes", "Reported-by", "Signed-off-by", "Co-authored-by", "Assisted-by", "Follow-up to",
             "Ref")


def mine_commits(snap: Snapshot) -> list[Candidate]:
    try:
        messages = commit_messages(snap.mirror, snap.commit, 500)
    except HistoryError:
        return []
    if len(messages) < 50:
        return []
    subjects = [m.strip().splitlines()[0] if m.strip() else "" for _, m in messages]
    conventional = [i for i, s in enumerate(subjects) if _CONVENTIONAL_RE.match(s)]
    area = [i for i, s in enumerate(subjects) if not _CONVENTIONAL_RE.match(s) and _AREA_RE.match(s)]
    pr_suffix = [i for i, s in enumerate(subjects) if re.search(r"\(#\d+\)$", s)]
    trailers = Counter()
    for _, m in messages:
        found = {t for t in _TRAILERS for line in m.splitlines() if re.match(rf"^{re.escape(t)}\b", line.strip(), re.I)}
        trailers.update(found)
    n = len(messages)
    parts, picks = [], []
    if len(conventional) / n >= 0.3:
        parts.append(f"Conventional Commits subjects ('fix: ...', 'feat(scope): ...') in {_pct(len(conventional), n)}")
        picks += conventional
    if len(area) / n >= 0.3:
        parts.append(f"'area: change' subjects (e.g. '{subjects[area[0]][:60]}') in {_pct(len(area), n)}")
        picks += area
    if len(pr_suffix) / n >= 0.3:
        parts.append(f"subjects ending with the pull-request number '(#N)' in {_pct(len(pr_suffix), n)}")
        picks += pr_suffix
    common = [(t, k) for t, k in trailers.most_common() if k / n >= 0.2]
    if common:
        parts.append("trailers " + ", ".join(f"'{t}' ({_pct(k, n)})" for t, k in common))
    if not parts:
        parts.append(f"plain sentence subjects (no common prefix); e.g. '{subjects[0][:60]}'")
    body = f"Commit messages (last {n} non-merge commits): " + "; ".join(parts) + "."
    shas = {sha for sha, _ in messages}
    chosen = [c for c in snap.history[:n] if c.sha in shas]
    if picks:
        picked = {messages[i][0] for i in picks}
        chosen = [c for c in chosen if c.sha in picked] or chosen
    evidence = [commit_evidence(c.sha, c.date, c.subject) for c in chosen[:MAX_EXAMPLES]]
    top_share = max([len(conventional), len(area), len(pr_suffix)] + [k for _, k in common]) / n
    return [Candidate(key="commits/style", kind="convention", title="Commit message style", body=body,
                      evidence=evidence, support=n, confidence=top_share, source="history",
                      eligible=top_share >= 0.5)]


def _toml_value(text: str, section: str, key: str) -> str | None:
    m = re.search(rf"^\[{re.escape(section)}\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if not m:
        return None
    v = re.search(rf"^{re.escape(key)}\s*=\s*(.+)$", m.group(1), re.M)
    return v.group(1).strip() if v else None


def mine_tooling(snap: Snapshot) -> list[Candidate]:
    found: list[str] = []
    evidence: list[dict] = []

    def cite(path: str) -> None:
        if (e := file_evidence(snap.checkout, path)):
            evidence.append(e)

    if "pyproject.toml" in snap.files:
        text = "\n".join(snap.lines("pyproject.toml"))
        tools = [t for t in ("ruff", "black", "isort", "mypy", "pyright", "pytest", "coverage", "flake8")
                 if re.search(rf"^\[tool\.{t}(\.|\])", text, re.M)]
        if tools:
            found.append("pyproject configures " + ", ".join(tools))
            length = _toml_value(text, "tool.ruff", "line-length") or _toml_value(text, "tool.black", "line-length")
            if length:
                found.append(f"line length {length}")
            cite("pyproject.toml")
    if ".pre-commit-config.yaml" in snap.files:
        hooks = re.findall(r"-\s+id:\s*([\w.-]+)", "\n".join(snap.lines(".pre-commit-config.yaml")))
        if hooks:
            found.append("pre-commit hooks: " + ", ".join(dict.fromkeys(hooks)))
            cite(".pre-commit-config.yaml")
    if "tox.ini" in snap.files:
        env = re.search(r"^envlist\s*=\s*(.+(?:\n\s+.+)*)", "\n".join(snap.lines("tox.ini")), re.M)
        found.append("tox" + (f" (envs: {' '.join(env.group(1).split())[:80]})" if env else ""))
        cite("tox.ini")
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
            cite("package.json")
    if "Makefile" in snap.files:
        targets = [t for t in re.findall(r"^([a-z][\w-]*):", "\n".join(snap.lines("Makefile")), re.M)
                   if t in ("all", "fmt", "format", "lint", "test", "check", "checksrc")]
        if targets:
            found.append("Makefile targets: " + ", ".join(dict.fromkeys(targets)))
            cite("Makefile")
    if ".editorconfig" in snap.files:
        width = re.search(r"max_line_length\s*=\s*(\d+)", "\n".join(snap.lines(".editorconfig")))
        if width:
            found.append(f".editorconfig max_line_length {width.group(1)}")
            cite(".editorconfig")
    if ".clang-format" in snap.files:
        width = re.search(r"ColumnLimit:\s*(\d+)", "\n".join(snap.lines(".clang-format")))
        found.append(".clang-format" + (f" (ColumnLimit {width.group(1)})" if width else ""))
        cite(".clang-format")
    if "scripts/checksrc.pl" in snap.files:
        found.append("scripts/checksrc.pl checks source style")
        cite("scripts/checksrc.pl")
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
                      body="Tooling: " + "; ".join(found) + ".", evidence=evidence, support=len(evidence),
                      confidence=1.0, source="code", eligible=bool(evidence))]


# ── history: co-change, dependencies, moves, origins ───────────────────

def mine_cochange(snap: Snapshot, *, max_items: int = 300, per_file: int = 300) -> list[Candidate]:
    touching: dict[str, list[Commit]] = defaultdict(list)
    for c in snap.history:
        if not c.files or len(c.files) > 30:
            continue
        for _, p in c.files:
            p = snap.canonical(p)
            if p in snap.files and _is_source_path(p) and len(touching[p]) < per_file:
                touching[p].append(c)
    out = []
    for path, commits in sorted(touching.items(), key=lambda kv: -len(kv[1]))[:max_items]:
        if len(commits) < 8:
            continue
        partners = Counter()
        for c in commits:
            partners.update({snap.canonical(p) for _, p in c.files} - {path})
        top = [(p, n) for p, n in partners.most_common(12) if p in snap.files and n >= 4 and n / len(commits) >= 0.2]
        if not top:
            continue
        top = top[:6]
        body = (f"When {path} changes, these files usually change in the same commit (of its last {len(commits)} "
                "commits): " + ", ".join(f"{p} {_pct(n, len(commits))}" for p, n in top) + ".")
        lead = top[0][0]
        together = [c for c in commits if lead in {snap.canonical(p) for _, p in c.files}][:3]
        evidence = [e for e in [file_evidence(snap.checkout, path)] if e]
        evidence += [commit_evidence(c.sha, c.date, c.subject) for c in together]
        out.append(Candidate(key=f"cochange/{path}", kind="co_change", title=f"Changes with {path}", body=body,
                             evidence=evidence, support=top[0][1], confidence=top[0][1] / len(commits),
                             source="history", scope={"paths": [path]}, eligible=top[0][1] >= 5))
    return out


TEST_SUPPORT_RE = re.compile(r"(^|/)(helpers?|fixtures?|testdata|conftest\.py$|__snapshots__)(/|$)")


def mine_test_homes(snap: Snapshot, *, max_items: int = 300, per_file: int = 300) -> list[Candidate]:
    """The existing test files a source file's changes add tests to, so a change extends them
    instead of starting a new test file."""
    touching: dict[str, list[Commit]] = defaultdict(list)
    for c in snap.history:
        if not c.files or len(c.files) > 30:
            continue
        for _, p in c.files:
            p = snap.canonical(p)
            if p in snap.files and _is_source_path(p) and len(touching[p]) < per_file:
                touching[p].append(c)
    out = []
    for path, commits in sorted(touching.items(), key=lambda kv: -len(kv[1]))[:max_items]:
        tests = Counter()
        for c in commits:
            tests.update({q for _, p in c.files if (q := snap.canonical(p)) in snap.files and path_role(q) == "test"
                          and not TEST_SUPPORT_RE.search(q)})
        with_tests = sum(1 for c in commits if any(path_role(snap.canonical(p)) == "test" for _, p in c.files))
        top = [(p, n) for p, n in tests.most_common(3) if n >= 3 and n / len(commits) >= 0.15]
        if not top:
            continue
        body = (f"Tests for {path} go in the existing " + ", ".join(f"{p} ({n} of {len(commits)} commits)"
                                                                    for p, n in top) + ".")
        together = [c for c in commits if top[0][0] in {snap.canonical(p) for _, p in c.files}][:3]
        evidence = [e for e in [file_evidence(snap.checkout, top[0][0])] if e]
        evidence += [commit_evidence(c.sha, c.date, c.subject) for c in together]
        out.append(Candidate(key=f"testhome/{path}", kind="co_change", title=f"Tests for {path}", body=body,
                             evidence=evidence, support=top[0][1], confidence=top[0][1] / max(with_tests, 1),
                             source="history", scope={"paths": [path]}, eligible=top[0][1] >= 4))
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


_MANIFESTS: dict[str, tuple[Callable[[str], tuple[set[str], str | None]], str]] = {
    "pyproject.toml": (_deps_python, "Python"), "setup.py": (_deps_python, "Python"),
    "go.mod": (_deps_go, "Go"), "package.json": (_deps_npm, "Node.js"),
}


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
            if gone or (prev[4] != cur[4] and cur[4]):
                cur = _author_commit(snap.mirror, prev[0], cur, manifest)
            for dep in gone:
                removed[dep] = cur
            if prev[4] != cur[4] and cur[4]:
                runtime_changes.append((prev[4], cur))
        for dep, (sha, date, subject, *_rest) in sorted(removed.items()):
            out.append(Candidate(
                key=f"history/dependency-removed/{dep}", kind="history", title=f"{dep} is no longer a dependency",
                body=f"{dep} was removed from {manifest} in {sha[:10]} ({date[:10]}): '{subject}'. It is not a "
                     f"dependency at the indexed commit.",
                evidence=[commit_evidence(sha, date, subject)], support=1, confidence=1.0, source="history",
                scope={"paths": [manifest]}, eligible=True))
        if runtime_changes and current_runtime:
            recent = runtime_changes[-3:]
            steps = "; ".join(f"{old or '?'} -> {new[4]} in {new[0][:10]} ({new[1][:10]}, '{new[2][:80]}')"
                              for old, new in reversed(recent))
            out.append(Candidate(
                key=f"history/runtime/{runtime.lower()}", kind="history", title=f"Supported {runtime} versions",
                body=f"{runtime} requirement in {manifest} is {current_runtime}. Recent changes, newest first: {steps}.",
                evidence=[commit_evidence(n[0], n[1], n[2]) for _, n in reversed(recent)], support=len(recent),
                confidence=1.0, source="history", scope={"paths": [manifest]}, eligible=True))
    return out


def mine_moves(snap: Snapshot) -> list[Candidate]:
    out = []
    for c in snap.history:
        groups: dict[tuple[str, str], int] = Counter()
        for old, new in c.renames:
            o, n = PurePosixPath(old).parts, PurePosixPath(new).parts
            k = 0
            while k < min(len(o), len(n)) and o[len(o) - 1 - k] == n[len(n) - 1 - k]:
                k += 1
            if k == 0 or k == len(o) and k == len(n):
                continue
            groups[("/".join(o[:len(o) - k]) or ".", "/".join(n[:len(n) - k]) or ".")] += 1
        for (src, dst), count in groups.items():
            if count < 5 or (dst != "." and not any(p.startswith(dst + "/") for p in snap.files)):
                continue
            out.append(Candidate(
                key=f"history/move/{src}->{dst}"[:255], kind="history", title=f"{src}/ moved to {dst}/",
                body=f"{count} files moved from {src}/ to {dst}/ in {c.sha[:10]} ({c.date[:10]}): '{c.subject}'.",
                evidence=[commit_evidence(c.sha, c.date, c.subject)], support=count, confidence=1.0,
                source="history", eligible=True))
    return out


def mine_origins(snap: Snapshot, *, max_items: int = 300) -> list[Candidate]:
    sizes = Counter(c.path for c in snap.source())
    candidates = {p for p, n in sizes.items() if n >= 3}
    origin: dict[str, Commit] = {}
    for c in snap.history:  # newest first: the last "A" seen is the oldest
        for status, p in c.files:
            p = snap.canonical(p)
            if status == "A" and p in candidates:
                origin[p] = c
    out = []
    for path, c in sorted(origin.items(), key=lambda kv: -sizes[kv[0]])[:max_items]:
        out.append(Candidate(
            key=f"history/origin/{path}"[:255], kind="history", title=f"Origin of {path}",
            body=f"{path} was added in {c.sha[:10]} ({c.date[:10]}): '{c.subject}'.",
            evidence=[commit_evidence(c.sha, c.date, c.subject)], support=1, confidence=1.0, source="history",
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


def mine_playbooks(snap: Snapshot, *, recent: int = 40) -> list[SkillCandidate]:
    by_pattern: dict[str, list[Commit]] = defaultdict(list)
    for c in snap.history:
        if not c.files or len(c.files) > 30:
            continue
        for pat in {addition_pattern(snap.canonical(p)) for s, p in c.files if s == "A"}:
            if len(by_pattern[pat]) < recent:
                by_pattern[pat].append(c)
    out = []
    for pat, commits in sorted(by_pattern.items()):
        if len(commits) < 5 or pat == "*" or pat.endswith("/*"):
            continue
        changed = Counter()
        for c in commits:
            changed.update({snap.canonical(p) for s, p in c.files if s == "M"})
        steps = [(p, n) for p, n in changed.most_common(15) if p in snap.files and n / len(commits) >= 0.5]
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
            scope={"paths": [_glob(pat)] + [p for p, _ in steps]}, eligible=len(commits) >= 5))
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
    "history": lambda s: mine_dependencies(s) + mine_moves(s) + mine_origins(s),
}


def tracked_files(checkout: Path) -> set[str]:
    return set(_git(checkout, "ls-files").splitlines())
