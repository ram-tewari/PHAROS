"""Checkable rules: typed predicates over a change, and the rule that activates them.

A convention is only as good as its record. Instead of a sentence with a
confidence number, a miner attaches a :class:`Check` to the items it can test:
a predicate that says whether it *applies* to a change and whether the change
*holds* to it. The backtest (``backtest.py``) runs each check on commits that
came after the ones it was learned from, and :func:`decide` turns that record
into the item's status and strength.

A :class:`Change` is what a commit or an uncommitted diff does: the files it
adds, modifies, deletes or renames with their added and removed lines, and
the commit message when there is one. :func:`parse_diff` reads ``git diff`` /
``git show`` output, so the same check runs on a historical commit and on a
diff an agent is about to submit.

Adding a predicate kind is one ``@register`` dataclass with ``applies``,
``holds`` and ``render``; its JSON form is its fields plus ``kind``.
"""

from __future__ import annotations

import dataclasses
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import PurePosixPath
from typing import ClassVar

# ── the change ─────────────────────────────────────────────────────────

MAX_LINES_PER_FILE = 4000  # longer diffs (generated files, vendored code) keep their first lines


@dataclass
class FileChange:
    status: str  # A (added; copies count as added), M, D, R (renamed)
    path: str  # the path after the change (for a deletion, the deleted path)
    old_path: str | None = None  # for a rename
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


@dataclass
class Change:
    """One commit (diffed against its first parent) or one uncommitted diff."""

    files: list[FileChange]
    message: str | None = None
    sha: str | None = None
    date: str | None = None
    merge: bool = False  # a merge commit: the diff is the whole merged branch
    lines: bool = True  # False when only the file list was loaded (a change too large to read)

    @property
    def subject(self) -> str:
        return (self.message or "").strip().split("\n", 1)[0]

    def touched(self, *, deletions: bool = True) -> set[str]:
        """Every path the change touches (both names of a rename)."""
        out = set()
        for f in self.files:
            if f.status == "D" and not deletions:
                continue
            out.add(f.path)
            if f.old_path:
                out.add(f.old_path)
        return out

    def added_files(self) -> list[FileChange]:
        return [f for f in self.files if f.status == "A"]

    def describe(self) -> dict:
        return {"sha": (self.sha or "")[:12], "date": (self.date or "")[:10], "subject": self.subject[:120]}


def _unquote(path: str) -> str:
    if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
        path = path[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape").encode(
            "latin-1", "replace").decode("utf-8", "replace")
    return path


def _strip_prefix(path: str) -> str | None:
    path = _unquote(path.strip())
    if path == "/dev/null":
        return None
    return path[2:] if path[:2] in ("a/", "b/") else path


_HEADER_RE = re.compile(r'^diff --git (?:"a/(.+?)"|a/(.+?)) (?:"b/(.+)"|b/(.+))$')


def parse_diff(text: str) -> list[FileChange]:
    """The files of a unified diff (``git diff``, ``git show``, ``git format-patch``), with their lines."""
    files: list[FileChange] = []
    cur: FileChange | None = None
    in_hunk = False
    for line in text.splitlines():
        if line.startswith("diff --git "):
            m = _HEADER_RE.match(line)
            new = _unquote(f'"{m.group(3)}"') if m and m.group(3) else m.group(4) if m else line.split(" b/")[-1]
            cur = FileChange(status="M", path=new)
            files.append(cur)
            in_hunk = False
            continue
        if cur is None:
            continue
        if line.startswith("@@"):
            in_hunk = True
            continue
        if in_hunk and line[:1] in "+- \\":
            if line.startswith("+") and len(cur.added) < MAX_LINES_PER_FILE:
                cur.added.append(line[1:])
            elif line.startswith("-") and len(cur.removed) < MAX_LINES_PER_FILE:
                cur.removed.append(line[1:])
            continue
        in_hunk = False
        if line.startswith("new file mode"):
            cur.status = "A"
        elif line.startswith("deleted file mode"):
            cur.status = "D"
        elif line.startswith("rename from "):
            cur.status, cur.old_path = "R", _unquote(line[len("rename from "):])
        elif line.startswith("rename to "):
            cur.path = _unquote(line[len("rename to "):])
        elif line.startswith("copy to "):
            cur.status, cur.path = "A", _unquote(line[len("copy to "):])
        elif line.startswith("--- "):
            old = _strip_prefix(line[4:])
            if old is None:
                cur.status = "A"
        elif line.startswith("+++ "):
            new = _strip_prefix(line[4:])
            if new is None:
                cur.status = "D"
            elif cur.status != "R":
                cur.path = new
    return files


def change_from_diff(text: str, message: str | None = None) -> Change:
    """An uncommitted change: ``git diff`` output and, optionally, the message it will be committed with."""
    return Change(files=parse_diff(text), message=message)


# ── paths ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=4096)
def _glob_re(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def glob_match(pattern: str, path: str) -> bool:
    """Path glob with ``**`` (any depth), ``*`` and ``?`` (within one segment)."""
    return bool(_glob_re(pattern).match(path))


def language_of(path: str) -> str | None:
    from ..codeintel.languages import detect_language

    spec = detect_language(path)
    return spec.name if spec else None


def role_of(path: str) -> str:
    """``source`` (code with a parser, not a test, doc or example), ``test``, ``docs``, ``example`` or
    ``other`` (a changelog, configuration, data)."""
    from ..codeintel.languages import detect_language
    from ..codeintel.retrieval import path_role

    role = path_role(path)
    spec = detect_language(path)
    if role == "source":
        return "source" if spec and spec.parser else "other"
    if role == "test" and not spec:
        return "test-data"
    return role


@dataclass(frozen=True)
class Paths:
    """A set of paths: any of ``globs`` (all paths when empty), narrowed by role and language,
    minus ``exclude``."""

    globs: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    def match(self, path: str) -> bool:
        if self.globs and not any(glob_match(g, path) for g in self.globs):
            return False
        if self.exclude and any(glob_match(g, path) for g in self.exclude):
            return False
        if self.roles and role_of(path) not in self.roles:
            return False
        return not self.languages or language_of(path) in self.languages

    def describe(self) -> str:
        what = " or ".join(self.globs) if self.globs else ""
        if self.roles or self.languages:
            kind = " ".join(x for x in ("/".join(self.languages), " or ".join(self.roles)) if x) + " files"
            what = f"{kind} matching {what}" if what else kind
        if self.exclude:
            what += " (except " + ", ".join(self.exclude) + ")"
        return what or "any file"

    def to_json(self) -> dict:
        return {k: list(v) for k, v in dataclasses.asdict(self).items() if v}

    @classmethod
    def from_json(cls, data: dict | None) -> Paths:
        data = data or {}
        return cls(**{k: tuple(data.get(k) or ()) for k in ("globs", "roles", "languages", "exclude")})


def files_in(change: Change, scope: Paths) -> list[FileChange]:
    return [f for f in change.files if f.status != "D" and scope.match(f.path)]


# ── definitions in added lines (for naming and signature checks) ────────

_JS = (r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)",
       r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)",
       r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?"
       r"(?:function\b|\([^)]*\)\s*(?::[^=]+)?=>|[A-Za-z_$][\w$]*\s*=>)")
_C_KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof", "do", "else", "case", "defined", "typedef"}
_DEFINITIONS: dict[str, list[tuple[re.Pattern, str]]] = {
    "python": [(re.compile(r"^(?:async\s+)?def\s+([A-Za-z_]\w*)"), "function"),
               (re.compile(r"^\s+(?:async\s+)?def\s+([A-Za-z_]\w*)"), "method"),
               (re.compile(r"^\s*class\s+([A-Za-z_]\w*)"), "class")],
    "go": [(re.compile(r"^func\s+\([^)]*\)\s*([A-Za-z_]\w*)"), "method"),
           (re.compile(r"^func\s+([A-Za-z_]\w*)"), "function")],
    "rust": [(re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+)?(?:async\s+)?(?:unsafe\s+)?"
                         r"(?:extern\s+\"\w+\"\s+)?fn\s+([A-Za-z_]\w*)"), "function")],
    "c": [(re.compile(r"^#\s*define\s+([A-Za-z_]\w*)\("), "macro"),
          (re.compile(r"^(?![\s#/{}])(?:[A-Za-z_][\w\s\*]*?[\s\*])?([A-Za-z_]\w*)\s*\([^;=]*$"), "function")],
    "javascript": [(re.compile(p), k) for p, k in zip(_JS, ("function", "class", "function"), strict=True)],
    "typescript": [(re.compile(p), k) for p, k in zip(_JS, ("function", "class", "function"), strict=True)],
    "java": [(re.compile(r"^\s*(?:public\s+|private\s+|protected\s+|abstract\s+|final\s+|static\s+)*"
                         r"(?:class|interface|enum|record)\s+([A-Za-z_]\w*)"), "class")],
}
_DEFINITIONS["cpp"] = _DEFINITIONS["c"]


def definitions(lines: list[str], language: str) -> list[tuple[str, str, str]]:
    """(kind, name, line) for each definition that starts on one of ``lines``."""
    out = []
    for line in lines:
        for pattern, kind in _DEFINITIONS.get(language, []):
            m = pattern.match(line)
            if m and m.group(1) not in _C_KEYWORDS:
                out.append((kind, m.group(1), line))
                break
    return out


def new_definitions(f: FileChange, language: str) -> list[tuple[str, str, str]]:
    """Definitions a file change adds: in its added lines, under a name its removed lines did not define."""
    before = {name for _, name, _ in definitions(f.removed, language)}
    return [d for d in definitions(f.added, language) if d[1] not in before]


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


STYLE_FITS = {"MixedCaps": {"camelCase", "PascalCase"}}


def test_pattern(path: str) -> str:
    """Where a test file lives, with its varying part abstracted: ``tests/test_*.py``, ``*_test.go``."""
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


TEST_SUPPORT_RE = re.compile(r"(^|/)(helpers?|fixtures?|testdata|conftest\.py$|__snapshots__)(/|$)")


# ── predicates ─────────────────────────────────────────────────────────

REGISTRY: dict[str, type[Check]] = {}


def register(cls):
    REGISTRY[cls.kind] = cls
    return cls


class Check:
    """A predicate over a :class:`Change`. Subclasses are frozen dataclasses."""

    kind: ClassVar[str] = ""

    def applies(self, change: Change) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError

    def holds(self, change: Change) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError

    def render(self) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def evaluate(self, change: Change) -> bool | None:
        """None when the rule does not apply, else whether the change holds to it."""
        return self.holds(change) if self.applies(change) else None

    def to_json(self) -> dict:
        out: dict = {"kind": self.kind}
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            out[f.name] = value.to_json() if isinstance(value, Paths) else list(value) if isinstance(
                value, tuple) else value
        return out


def check_from_json(data: dict | None) -> Check | None:
    """The check a stored JSON form describes; None for no check or an unknown kind."""
    if not data or data.get("kind") not in REGISTRY:
        return None
    cls = REGISTRY[data["kind"]]
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        if f.type.startswith("Paths"):
            value = None if value is None else Paths.from_json(value)
        elif f.type.startswith("tuple"):
            value = tuple(value or ())
        kwargs[f.name] = value
    return cls(**kwargs)


def _count_files(change: Change) -> int:
    return len(change.files)


@register
@dataclass(frozen=True)
class Companion(Check):
    """Touching a file in ``when`` implies touching one in ``then`` (co-change, test homes, changelog)."""

    kind: ClassVar[str] = "companion"
    when: Paths
    then: Paths
    max_files: int = 30  # larger changes are sweeps and say nothing about habits
    # Only changes that also touch a file in ``given`` count (a test home: *which* test file, given that
    # the change touches tests at all). None: every change that touches ``when``.
    given: Paths | None = None

    def applies(self, change: Change) -> bool:
        touched = change.touched(deletions=False)
        return (_count_files(change) <= self.max_files and any(self.when.match(p) for p in touched)
                and (self.given is None or any(self.given.match(p) and not self.when.match(p) for p in touched)))

    def holds(self, change: Change) -> bool:
        return any(self.then.match(p) and not self.when.match(p) for p in change.touched())

    def render(self) -> str:
        given = f" and {self.given.describe()}" if self.given else ""
        return (f"A change of at most {self.max_files} files that touches {self.when.describe()}{given} "
                f"also touches {self.then.describe()}.")


@register
@dataclass(frozen=True)
class NewFileCompanion(Check):
    """Adding a file in ``new`` implies touching (or, with ``then_added``, adding) a file in ``then``."""

    kind: ClassVar[str] = "new_file_companion"
    new: Paths
    then: Paths
    then_added: bool = False
    max_files: int = 30

    def applies(self, change: Change) -> bool:
        return _count_files(change) <= self.max_files and any(self.new.match(f.path) for f in change.added_files())

    def holds(self, change: Change) -> bool:
        pool = [f.path for f in change.added_files()] if self.then_added else list(change.touched())
        return any(self.then.match(p) and not self.new.match(p) for p in pool)

    def render(self) -> str:
        verb = "adds a new" if self.then_added else "touches"
        return f"A change that adds a new {self.new.describe()} also {verb} {self.then.describe()}."


@register
@dataclass(frozen=True)
class NewTestFileLocation(Check):
    """New test files go where the existing ones live (``patterns`` from :func:`test_pattern`)."""

    kind: ClassVar[str] = "new_test_location"
    patterns: tuple[str, ...]
    files: Paths = Paths(roles=("test",))

    def _new_tests(self, change: Change) -> list[str]:
        from ..codeintel.retrieval import _EXAMPLE_PATH_RE

        return [f.path for f in change.added_files() if self.files.match(f.path) and language_of(f.path)
                and not TEST_SUPPORT_RE.search(f.path) and not _EXAMPLE_PATH_RE.search(f.path)]

    def applies(self, change: Change) -> bool:
        return bool(self._new_tests(change))

    def holds(self, change: Change) -> bool:
        return all(test_pattern(p) in self.patterns for p in self._new_tests(change))

    def render(self) -> str:
        return "A new test file goes in " + ", ".join(self.patterns) + "."


@register
@dataclass(frozen=True)
class Naming(Check):
    """New ``symbol`` definitions (function, method, class, macro) in ``language`` follow ``style``.
    Names of one word fit every style and are ignored."""

    kind: ClassVar[str] = "naming"
    language: str
    symbol: str
    style: str
    scope: Paths = Paths(roles=("source",))

    def _names(self, change: Change) -> list[str]:
        names = []
        for f in files_in(change, self.scope):
            if language_of(f.path) != self.language:
                continue
            names += [name for kind, name, _ in new_definitions(f, self.language)
                      if kind == self.symbol and not (name.startswith("__") and name.endswith("__"))
                      and case_style(name)]
        return names

    def applies(self, change: Change) -> bool:
        return change.lines and bool(self._names(change))

    def holds(self, change: Change) -> bool:
        fits = STYLE_FITS.get(self.style, {self.style})
        return all(case_style(n) in fits for n in self._names(change))

    def render(self) -> str:
        return (f"New {self.language} {self.symbol} names with more than one word in "
                f"{self.scope.describe()} are {self.style}.")


@register
@dataclass(frozen=True)
class Signature(Check):
    """New one-line ``symbol`` definitions in ``language`` match ``require`` (a return annotation)."""

    kind: ClassVar[str] = "signature"
    language: str
    symbols: tuple[str, ...]
    require: str
    label: str
    complete: str = r":\s*(#.*)?$"  # a definition line counts only when the signature ends on it
    scope: Paths = Paths(roles=("source",))

    def _lines(self, change: Change) -> list[str]:
        done = re.compile(self.complete)
        out = []
        for f in files_in(change, self.scope):
            if language_of(f.path) == self.language:
                out += [line for kind, _, line in new_definitions(f, self.language)
                        if kind in self.symbols and done.search(line)]
        return out

    def applies(self, change: Change) -> bool:
        return change.lines and bool(self._lines(change))

    def holds(self, change: Change) -> bool:
        need = re.compile(self.require)
        return all(need.search(line) for line in self._lines(change))

    def render(self) -> str:
        return f"New {self.language} {'/'.join(self.symbols)} definitions {self.label}."


@register
@dataclass(frozen=True)
class Message(Check):
    """The commit message has a subject matching ``subject`` and/or a ``trailer`` line.
    Merge commits are written by the forge, not the author, so the rule does not apply to them."""

    kind: ClassVar[str] = "message"
    label: str
    subject: str = ""
    trailer: str = ""

    def applies(self, change: Change) -> bool:
        return bool(change.message and change.message.strip()) and not change.merge

    def holds(self, change: Change) -> bool:
        if self.subject and not re.search(self.subject, change.subject):
            return False
        if self.trailer:
            want = re.compile(rf"^{re.escape(self.trailer)}\b", re.I)
            return any(want.match(line.strip()) for line in (change.message or "").splitlines()[1:])
        return True

    def render(self) -> str:
        return f"Commit messages {self.label}."


def _added_lines(change: Change, scope: Paths) -> list[str]:
    return [line for f in files_in(change, scope) for line in f.added]


@register
@dataclass(frozen=True)
class Forbidden(Check):
    """Added lines in ``scope`` never match ``pattern`` (a dropped dependency, a deprecated API).
    The rule applies when the change adds a line matching ``when`` there (an import, any code)."""

    kind: ClassVar[str] = "forbidden"
    pattern: str
    label: str
    scope: Paths
    when: str = r"\S"

    def applies(self, change: Change) -> bool:
        when = re.compile(self.when)
        return change.lines and any(when.search(line) for line in _added_lines(change, self.scope))

    def holds(self, change: Change) -> bool:
        bad = re.compile(self.pattern)
        return not any(bad.search(line) for line in _added_lines(change, self.scope))

    def render(self) -> str:
        return f"Changes to {self.scope.describe()} do not add {self.label}."


@register
@dataclass(frozen=True)
class AddedPattern(Check):
    """When added lines in ``scope`` match ``when``, other added lines there match ``then``."""

    kind: ClassVar[str] = "added_pattern"
    when: str
    then: str
    label: str
    scope: Paths

    def applies(self, change: Change) -> bool:
        when = re.compile(self.when)
        return change.lines and any(when.search(line) for line in _added_lines(change, self.scope))

    def holds(self, change: Change) -> bool:
        then = re.compile(self.then)
        return any(then.search(line) for line in _added_lines(change, self.scope))

    def render(self) -> str:
        return f"In {self.scope.describe()}, {self.label}."


@register
@dataclass(frozen=True)
class NewFileContains(Check):
    """Every new file in ``new`` (of at least ``min_lines`` lines) has a line matching ``pattern``."""

    kind: ClassVar[str] = "new_file_contains"
    new: Paths
    pattern: str
    label: str
    min_lines: int = 5

    def _files(self, change: Change) -> list[FileChange]:
        return [f for f in change.added_files() if self.new.match(f.path)
                and sum(bool(line.strip()) for line in f.added) >= self.min_lines]

    def applies(self, change: Change) -> bool:
        return change.lines and bool(self._files(change))

    def holds(self, change: Change) -> bool:
        want = re.compile(self.pattern)
        return all(any(want.search(line) for line in f.added) for f in self._files(change))

    def render(self) -> str:
        return f"A new {self.new.describe()} {self.label}."


# ── activation: what a hold-out record earns ───────────────────────────

def wilson_lower(held: int, applied: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval for ``held`` successes in ``applied`` trials (95 %)."""
    if applied <= 0:
        return 0.0
    p = held / applied
    denom = 1 + z * z / applied
    centre = p + z * z / (2 * applied)
    margin = z * math.sqrt(p * (1 - p) / applied + z * z / (4 * applied * applied))
    return max(0.0, (centre - margin) / denom)


@dataclass(frozen=True)
class Activation:
    """When a checkable rule is served, and how.

    ``window`` first-parent commits before the learned commit are held out: the miners run on the
    history before them, and each rule is checked on them. A rule that applied at least
    ``min_applied`` times and whose Wilson lower bound clears ``min_lower`` is a **requirement**
    (active, served as "do this"). One that applied as often and clears only ``observe_lower`` is an
    **observation** (active, served only on request). One that applied too rarely stays
    ``proposed`` (untested); one below both bounds goes ``stale`` with its record."""

    # Chosen on development mirrors only (docs/benchmarks/phase3-s2-dev-2026-11.md): learning 400
    # first-parent commits before their HEAD and checking the next 200, these gave the most rules
    # for their precision. A rule must apply at least 10 times before it can be required.
    window: int = 600
    min_applied: int = 10
    min_lower: float = 0.6
    observe_lower: float = 0.2


DEFAULT_ACTIVATION = Activation()

REQUIREMENT, OBSERVATION, ADVISORY = "requirement", "observation", "advisory"


@dataclass(frozen=True)
class Decision:
    status: str  # active | proposed | stale
    strength: str  # requirement | observation | advisory
    outcome: str  # requirement | observation | untested | changed | failed | not-run
    reason: str


def decide(check: dict | None, record: dict | None, activation: Activation = DEFAULT_ACTIVATION) -> Decision:
    """Status and strength for a checkable rule from its hold-out ``record`` (see ``backtest.py``).

    ``record`` is the rule as the miners derived it before the hold-out window, checked on that
    window. It counts only if that rule is the same predicate as ``check`` (the rule derived now);
    a rule that changed since has not been tested."""
    if record is None:
        return Decision("proposed", OBSERVATION, "not-run", "no hold-out test: the rule was not derived before the "
                                                            "hold-out window, or the backtest did not run")
    if record.get("check") != check:
        return Decision("proposed", OBSERVATION, "changed",
                        "the rule derived before the hold-out window was different; untested")
    applied, held = record.get("applied", 0), record.get("held", 0)
    lower = wilson_lower(held, applied)
    seen = f"applied {applied} times in the hold-out window and held {held} times"
    if applied < activation.min_applied:
        return Decision("proposed", OBSERVATION, "untested", f"{seen}: fewer than {activation.min_applied}")
    if lower >= activation.min_lower:
        return Decision("active", REQUIREMENT, "requirement", f"{seen} (lower bound {lower:.2f})")
    if lower >= activation.observe_lower:
        return Decision("active", OBSERVATION, "observation",
                        f"{seen} (lower bound {lower:.2f}): a pattern, not a requirement")
    return Decision("stale", OBSERVATION, "failed", f"{seen} (lower bound {lower:.2f})")


def holdout_sentence(record: dict | None, rule: str) -> str:
    """What the hold-out test measured, in words, or '' when there was none."""
    if not record or not record.get("window"):
        return ""
    w = record["window"]
    applied, held = record.get("applied", 0), record.get("held", 0)
    where = f"the {w['commits']} first-parent commits after {w['from'][:10]}"
    rule = rule.rstrip(".")
    if not applied:
        return f" Checked on {where}, the rule \"{rule}\" never applied."
    return f" Checked on {where}, the rule \"{rule}\" applied {applied} times and held {held} times."
