"""Checkable rules: each predicate on synthetic changes and diffs, JSON forms, and the activation rule."""

import os
import subprocess

import pytest

from app.learning.checks import (
    REGISTRY,
    Activation,
    AddedPattern,
    Change,
    Companion,
    FileChange,
    Forbidden,
    Message,
    Naming,
    NewFileCompanion,
    NewFileContains,
    NewTestFileLocation,
    Paths,
    Signature,
    change_from_diff,
    check_from_json,
    decide,
    holdout_sentence,
    parse_diff,
    wilson_lower,
)


def change(*files, message=None, merge=False, lines=True):
    out = []
    for f in files:
        if isinstance(f, FileChange):
            out.append(f)
        else:
            status, path = f.split(" ", 1)
            out.append(FileChange(status, path))
    return Change(files=out, message=message, merge=merge, lines=lines)


DIFF = '''diff --git a/src/shop/cart.py b/src/shop/cart.py
index 1111111..2222222 100644
--- a/src/shop/cart.py
+++ b/src/shop/cart.py
@@ -10,0 +11,3 @@ class Cart:
+    def add_item(self, sku: str) -> None:
+        self.items.append(sku)
+
@@ -20 +23 @@ def total(cart):
-def total(cart):
+def total(cart) -> int:
diff --git a/tests/test_cart.py b/tests/test_cart.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/tests/test_cart.py
@@ -0,0 +1,2 @@
+def test_add_item():
+    assert True
diff --git a/old_name.py b/new_name.py
similarity index 90%
rename from old_name.py
rename to new_name.py
index 4444444..5555555 100644
--- a/old_name.py
+++ b/new_name.py
@@ -1 +1 @@
-import six
+import json
diff --git a/CHANGES.rst b/CHANGES.rst
deleted file mode 100644
index 6666666..0000000
--- a/CHANGES.rst
+++ /dev/null
@@ -1 +0,0 @@
-Changes
diff --git "a/docs/my file.md" "b/docs/my file.md"
index 7777777..8888888 100644
--- "a/docs/my file.md"
+++ "b/docs/my file.md"
@@ -1 +1 @@
-old
+new
'''


def test_parse_diff_reads_status_paths_and_lines():
    files = {f.path: f for f in parse_diff(DIFF)}
    assert set(files) == {"src/shop/cart.py", "tests/test_cart.py", "new_name.py", "CHANGES.rst", "docs/my file.md"}
    cart = files["src/shop/cart.py"]
    assert cart.status == "M" and cart.added[0] == "    def add_item(self, sku: str) -> None:"
    assert cart.removed == ["def total(cart):"]
    assert files["tests/test_cart.py"].status == "A"
    assert (files["new_name.py"].status, files["new_name.py"].old_path) == ("R", "old_name.py")
    assert files["CHANGES.rst"].status == "D"
    c = change_from_diff(DIFF, message="cart: add items\n\nFixes: #12")
    assert c.subject == "cart: add items" and c.touched() >= {"old_name.py", "new_name.py", "CHANGES.rst"}
    assert "CHANGES.rst" not in c.touched(deletions=False)


def test_companion():
    rule = Companion(when=Paths(globs=("src/a.py",)), then=Paths(globs=("CHANGES.md",)), max_files=3)
    assert rule.evaluate(change("M src/a.py", "M CHANGES.md")) is True
    assert rule.evaluate(change("M src/a.py", "M src/b.py")) is False
    assert rule.evaluate(change("M src/b.py")) is None  # does not apply
    assert rule.evaluate(change("D src/a.py")) is None  # deleting the file is not changing it
    assert rule.evaluate(change("M src/a.py", "M x", "M y", "M z")) is None  # a sweep of 4 files
    # A changelog rule over a role: any source file implies the changelog.
    log = Companion(when=Paths(roles=("source",)), then=Paths(globs=("CHANGES.md",)))
    assert log.evaluate(change("M README.md")) is None and log.evaluate(change("M lib/x.go")) is False
    # A test home: given that the change touches tests at all, it touches these.
    home = Companion(when=Paths(globs=("src/a.py",)), then=Paths(globs=("tests/test_a.py",)),
                     given=Paths(roles=("test",)))
    assert home.evaluate(change("M src/a.py")) is None
    assert home.evaluate(change("M src/a.py", "M tests/test_b.py")) is False
    assert home.evaluate(change("M src/a.py", "M tests/test_a.py")) is True


def test_new_file_companion():
    rule = NewFileCompanion(new=Paths(globs=("src/plugins/*.py",)), then=Paths(globs=("tests/test_*.py",)),
                            then_added=True)
    assert rule.evaluate(change("A src/plugins/x.py", "A tests/test_x.py")) is True
    assert rule.evaluate(change("A src/plugins/x.py", "M tests/test_x.py")) is False  # must be a new test file
    assert rule.evaluate(change("M src/plugins/x.py")) is None
    docs = NewFileCompanion(new=Paths(globs=("src/plugins/*.py",)), then=Paths(globs=("docs/index.rst",)))
    assert docs.evaluate(change("A src/plugins/y.py", "M docs/index.rst")) is True


def test_new_test_file_location():
    rule = NewTestFileLocation(patterns=("tests/test_*.py",))
    assert rule.evaluate(change("A tests/test_new.py")) is True
    assert rule.evaluate(change("A tests/unit/test_new.py")) is False
    assert rule.evaluate(change("A tests/conftest.py")) is None  # support code, not a test file
    assert rule.evaluate(change("M tests/test_old.py")) is None


def _file(path, added=(), removed=(), status="M"):
    return FileChange(status, path, added=list(added), removed=list(removed))


def test_naming_looks_only_at_new_multi_word_names():
    rule = Naming(language="python", symbol="function", style="snake_case")
    good = change(_file("shop/cart.py", ["def add_item(x):", "    return x"]))
    bad = change(_file("shop/cart.py", ["def addItem(x):"]))
    assert rule.evaluate(good) is True and rule.evaluate(bad) is False
    assert rule.evaluate(change(_file("shop/cart.py", ["def run(x):"]))) is None  # one word fits any style
    renamed = change(_file("shop/cart.py", ["def addItem(x, y):"], ["def addItem(x):"]))
    assert rule.evaluate(renamed) is None  # a changed signature is not a new name
    assert rule.evaluate(change(_file("tests/test_cart.py", ["def testAddItem():"]))) is None  # tests are out of scope
    method = Naming(language="python", symbol="method", style="snake_case")
    assert method.evaluate(change(_file("shop/cart.py", ["    def addItem(self):"]))) is False
    go = Naming(language="go", symbol="function", style="MixedCaps")
    assert go.evaluate(change(_file("cmd.go", ["func newCommand() *Command {"]))) is True
    assert go.evaluate(change(_file("cmd.go", ["func new_command() *Command {"]))) is False
    c = Naming(language="c", symbol="function", style="snake_case")
    assert c.evaluate(change(_file("lib/url.c", ["static CURLcode", "parse_url_host(struct Curl_URL *u)"]))) is True
    assert c.evaluate(change(_file("lib/url.c", ["  if(parseHost(u))"]))) is None  # a call, not a definition
    assert rule.evaluate(change(_file("shop/cart.py", ["def addItem(x):"]), lines=False)) is None


def test_signature_requires_a_return_type_on_complete_definitions():
    rule = Signature(language="python", symbols=("function", "method"), require=r"->", label="declare a return type")
    assert rule.evaluate(change(_file("shop/a.py", ["def total(cart) -> int:"]))) is True
    assert rule.evaluate(change(_file("shop/a.py", ["def total(cart):"]))) is False
    assert rule.evaluate(change(_file("shop/a.py", ["def total(", "    cart,"]))) is None  # signature continues


def test_message():
    conventional = Message(label="start with a type", subject=r"^(feat|fix)(\([^)]*\))?!?: ")
    assert conventional.evaluate(change(message="fix(cart): rounding")) is True
    assert conventional.evaluate(change(message="Fix rounding")) is False
    assert conventional.evaluate(change(message="Merge pull request #1", merge=True)) is None  # the forge wrote it
    assert conventional.evaluate(change()) is None  # an uncommitted diff with no message yet
    signed = Message(label="are signed off", trailer="Signed-off-by")
    assert signed.evaluate(change(message="x\n\nSigned-off-by: A <a@example.com>")) is True
    assert signed.evaluate(change(message="Signed-off-by: in the subject")) is False


def test_forbidden_applies_to_changes_that_add_imports():
    rule = Forbidden(pattern=r"^\s*(?:import\s+six\b|from\s+six(?:\.[\w.]+)?\s+import\b)", label="six",
                     scope=Paths(roles=("source", "test"), languages=("python",)), when=r"^\s*(?:import|from)\s")
    assert rule.evaluate(change(_file("shop/a.py", ["import json"]))) is True
    assert rule.evaluate(change(_file("shop/a.py", ["from six.moves import range"]))) is False
    assert rule.evaluate(change(_file("shop/a.py", ["x = 1"]))) is None  # adds no import
    assert rule.evaluate(change(_file("docs/a.py", ["import six"]))) is None  # docs are out of scope


def test_added_pattern_and_new_file_contains():
    rule = AddedPattern(when=r"DeprecationWarning", then=r"stacklevel\s*=\s*2", label="pass stacklevel=2",
                        scope=Paths(roles=("source",), languages=("python",)))
    assert rule.evaluate(change(_file("a.py", ["warnings.warn('x', DeprecationWarning, stacklevel=2)"]))) is True
    assert rule.evaluate(change(_file("a.py", ["warnings.warn('x', DeprecationWarning)"]))) is False
    assert rule.evaluate(change(_file("a.py", ["x = 1"]))) is None
    future = NewFileContains(new=Paths(globs=("**/*.py",), roles=("source",)),
                             pattern=r"^from __future__ import annotations\s*$", label="imports annotations")
    body = ["x = 1"] * 5
    assert future.evaluate(change(_file("pkg/m.py", ["from __future__ import annotations", *body], status="A"))) is True
    assert future.evaluate(change(_file("pkg/m.py", body, status="A"))) is False
    assert future.evaluate(change(_file("pkg/m.py", ["x = 1"], status="A"))) is None  # too short to count


EXAMPLES = [
    Companion(when=Paths(globs=("a.py",)), then=Paths(globs=("b.py",)), given=Paths(roles=("test",))),
    NewFileCompanion(new=Paths(globs=("p/*.py",)), then=Paths(globs=("docs/index.rst",)), then_added=False),
    NewTestFileLocation(patterns=("tests/test_*.py", "*_test.go")),
    Naming(language="go", symbol="method", style="MixedCaps"),
    Signature(language="python", symbols=("function",), require="->", label="declare a return type"),
    Message(label="carry a trailer", trailer="Fixes"),
    Forbidden(pattern="six", label="six", scope=Paths(languages=("python",), exclude=("vendor/**",))),
    AddedPattern(when="x", then="y", label="x implies y", scope=Paths()),
    NewFileContains(new=Paths(globs=("*.py",)), pattern="z", label="has z"),
]


def test_every_kind_round_trips_through_json():
    assert {type(c) for c in EXAMPLES} == set(REGISTRY.values())
    for check in EXAMPLES:
        data = check.to_json()
        assert data["kind"] == check.kind
        assert check_from_json(data) == check
        assert check.render().endswith(".")
    assert check_from_json({"kind": "nope"}) is None and check_from_json(None) is None


def _git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def test_a_commit_and_the_same_uncommitted_diff_give_the_same_verdict(tmp_path):
    from app.learning.backtest import load_changes

    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "cart.py").write_text("def total(cart):\n    return 0\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    (tmp_path / "shop" / "cart.py").write_text("def total(cart):\n    return 0\n\n\ndef addItem(cart):\n    pass\n")
    (tmp_path / "CHANGES.md").write_text("- add items\n")
    diff = _git(tmp_path, "diff", "HEAD")  # CHANGES.md is untracked: not in the diff yet
    _git(tmp_path, "add", "-A")
    staged = _git(tmp_path, "diff", "--cached")
    _git(tmp_path, "commit", "-q", "-m", "cart: add items")
    sha = _git(tmp_path, "rev-parse", "HEAD").strip()
    [commit] = load_changes(tmp_path, [sha])
    naming = Naming(language="python", symbol="function", style="snake_case")
    log = Companion(when=Paths(globs=("shop/cart.py",)), then=Paths(globs=("CHANGES.md",)))
    assert naming.evaluate(commit) is False and naming.evaluate(change_from_diff(staged)) is False
    assert log.evaluate(commit) is True and log.evaluate(change_from_diff(staged)) is True
    assert log.evaluate(change_from_diff(diff)) is False  # the changelog is not part of that diff
    assert commit.subject == "cart: add items" and not commit.merge


# ── activation ──────────────────────────────────────────────────────────

def test_wilson_lower_bound():
    assert wilson_lower(0, 0) == 0.0
    assert wilson_lower(10, 10) == pytest.approx(0.722, abs=1e-3)
    assert wilson_lower(3, 3) == pytest.approx(0.439, abs=1e-3)  # three successes prove little
    assert wilson_lower(45, 100) == pytest.approx(0.356, abs=1e-3)


CHECK = Companion(when=Paths(globs=("a.py",)), then=Paths(globs=("b.py",))).to_json()
ACT = Activation(window=200, min_applied=10, min_lower=0.7, observe_lower=0.2)


@pytest.mark.parametrize("applied,held,status,strength,outcome", [
    (30, 30, "active", "requirement", "requirement"),
    (30, 14, "active", "observation", "observation"),  # a 45 % companion is information, not a requirement
    (3, 3, "proposed", "observation", "untested"),  # applied too rarely to prove anything
    (30, 2, "stale", "observation", "failed"),
])
def test_decide(applied, held, status, strength, outcome):
    record = {"check": CHECK, "applied": applied, "held": held}
    d = decide(CHECK, record, ACT)
    assert (d.status, d.strength, d.outcome) == (status, strength, outcome)
    assert f"applied {applied} times" in d.reason


def test_decide_without_a_matching_record():
    assert decide(CHECK, None, ACT).outcome == "not-run"
    other = Companion(when=Paths(globs=("a.py",)), then=Paths(globs=("c.py",))).to_json()
    assert decide(CHECK, {"check": other, "applied": 50, "held": 50}, ACT).outcome == "changed"


def test_holdout_sentence_states_what_was_measured():
    record = {"window": {"from": "abcdef1234567", "to": "x", "commits": 200}, "applied": 12, "held": 11}
    text = holdout_sentence(record, "When a.py changes, b.py changes.")
    assert text == (' Checked on the 200 first-parent commits after abcdef1234, the rule "When a.py changes, '
                    'b.py changes" applied 12 times and held 11 times.')
    assert holdout_sentence(None, "x") == ""
