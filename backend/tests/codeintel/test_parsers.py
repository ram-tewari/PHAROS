"""AST extraction: every claimed language really uses its AST parser."""

import pytest

from app.codeintel.languages import AST_LANGUAGES, detect_language
from app.codeintel.parsers import grammar_status, parse_file

FIXTURE_FILES = {
    # path in the fixture repo -> (language, expected qualified symbols with line spans)
    "shop/auth.py": ("python", {"shop.auth.verify_password": (20, 24), "shop.auth.TokenSigner.verify": (47, 57)}),
    "web/client.js": ("javascript", {"web.client.login": (9, 18), "web.client.addToCart": (21, 29)}),
    "web/session.ts": ("typescript", {"web.session.tokenExpiry": (4, 7), "web.session.SessionManager.isLoggedIn": (14, 16)}),
    "tools/ratelimit/limiter.go": ("go", {"tools.ratelimit.limiter.NewBucket": (19, 21), "tools.ratelimit.limiter.Bucket.Allow": (24, 33)}),
    "native/src/lib.rs": ("rust", {"native.src.lib.crc32": (6, 16), "native.src.lib.Cents.fmt": (23, 25)}),
    "native/c/checksum.c": ("c", {"native.c.checksum.adler32": (6, 13)}),
    "native/cpp/geometry.cpp": ("cpp", {"native.cpp.geometry.shipping.volumetric_weight": (12, 14)}),
    "android/src/com/tinyshop/CartActivity.java": ("java", {"android.src.com.tinyshop.CartActivity.CartActivity.onRemoveClicked": (11, 14)}),
}


def test_all_grammars_are_installed():
    """CI guard: a missing tree-sitter package must fail loudly, not degrade."""
    assert grammar_status() == {g: "ok" for g in grammar_status()}


def test_claimed_languages():
    assert set(AST_LANGUAGES) == {"c", "cpp", "go", "java", "javascript", "python", "rust", "typescript"}


@pytest.mark.parametrize("path", sorted(FIXTURE_FILES))
def test_fixture_files_use_ast_with_correct_spans(path):
    from tests.codeintel.conftest import FIXTURE_REPO

    language, expected = FIXTURE_FILES[path]
    source = (FIXTURE_REPO / path).read_text()
    result = parse_file(path, source)
    assert result.language == language
    assert result.parser in ("python-ast", "tree-sitter")
    assert result.fallback_reason is None
    spans = {s.qualified_name: (s.start_line, s.end_line) for s in result.symbols}
    for name, span in expected.items():
        assert spans.get(name) == span, (name, spans)
    # Line numbers point at the definition itself.
    lines = source.splitlines()
    for sym in result.symbols:
        if sym.kind != "module":
            assert sym.name.split("@")[0].split(" ")[-1] in lines[sym.start_line - 1] + "".join(
                lines[sym.start_line : sym.start_line + 3]
            ) or sym.kind == "impl", sym


def test_python_details():
    src = '''"""Module doc."""
from .db import query as q
from . import helpers

@cache
@other
def fetch(user_id: int, *, fresh: bool = False) -> "User":
    """Load a user."""
    def inner():
        return q(user_id)
    return helpers.wrap(inner())

class Repo(Base, metaclass=Meta):
    def get(self, key, /, default=None, *args, **kw):
        return self._load(key)
'''
    r = parse_file("pkg/svc/users.py", src)
    by = {s.qualified_name: s for s in r.symbols}
    fetch = by["pkg.svc.users.fetch"]
    assert fetch.start_line == 5  # decorators included
    assert fetch.end_line == 11
    assert fetch.signature == 'def fetch(user_id: int, *, fresh: bool) -> "User":'.replace('"User"', "'User'")
    assert fetch.docstring == "Load a user."
    assert {"q", "wrap", "inner"} <= set(fetch.calls)
    assert "pkg.svc.users.inner" not in by  # closures belong to the enclosing function
    assert by["pkg.svc.users.Repo"].signature == "class Repo(Base, metaclass=Meta):"
    assert by["pkg.svc.users.Repo.get"].kind == "method"
    assert "/" in by["pkg.svc.users.Repo.get"].signature
    assert r.import_map["q"] == "pkg.svc.db.query"
    assert "pkg.svc.helpers" in r.imports
    assert by["pkg.svc.users"].docstring == "Module doc."


def test_unicode_and_multiline_line_numbers():
    src = "# 日本語のコメント ✓\n\n\nconst greet = (name) =>\n  `héllo ${name}`;\n\nfunction après() {\n  return greet('é');\n}\n"
    r = parse_file("i18n/greet.js", src)
    by = {s.name: s for s in r.symbols}
    assert (by["greet"].start_line, by["greet"].end_line) == (4, 5)
    assert (by["après"].start_line, by["après"].end_line) == (7, 9)
    assert "greet" in by["après"].calls


def test_go_method_qualified_by_receiver_and_doc_comment():
    src = "package a\n\n// Speak says hello.\nfunc (d *Dog) Speak() string {\n\treturn d.name\n}\n"
    r = parse_file("a/dog.go", src)
    speak = next(s for s in r.symbols if s.name == "Speak")
    assert speak.qualified_name == "a.dog.Dog.Speak"
    assert speak.kind == "method"
    assert speak.docstring == "Speak says hello."


def test_rust_impl_methods_qualified_by_type():
    src = "struct P;\nimpl std::fmt::Display for P {\n    fn fmt(&self) {}\n}\nimpl P { fn new() -> P { P } }\n"
    r = parse_file("src/p.rs", src)
    names = {s.qualified_name: s.kind for s in r.symbols}
    assert names["src.p.P.fmt"] == "method"
    assert names["src.p.P.new"] == "method"
    assert any(k == "impl" for k in names.values())


def test_syntax_error_falls_back_and_says_so():
    r = parse_file("bad.py", "def broken(:\n    pass\n")
    assert r.parser == "line-fallback"
    assert r.fallback_reason == "syntax_error"
    assert r.symbols and all(s.kind == "block" for s in r.symbols)


def test_unsupported_language_falls_back_with_reason():
    r = parse_file("script.rb", "\n".join(f"puts {i}" for i in range(130)))
    assert r.parser == "line-fallback"
    assert r.fallback_reason == "unsupported_language"
    # 60-line windows with 10 lines of overlap
    assert [(s.start_line, s.end_line) for s in r.symbols] == [(1, 60), (51, 110), (101, 130)]


def test_missing_grammar_is_reported_not_hidden(monkeypatch):
    from app.codeintel.parsers import treesitter_parser

    monkeypatch.setitem(treesitter_parser._load_errors, "go", "grammar_unavailable:tree-sitter-go")
    monkeypatch.delitem(treesitter_parser._parsers, "go", raising=False)
    r = parse_file("x.go", "package x\nfunc F() {}\n")
    assert r.parser == "line-fallback"
    assert r.fallback_reason == "grammar_unavailable:tree-sitter-go"


def test_non_source_files_are_ignored():
    assert parse_file("README.md", "# hi") is None
    assert detect_language("assets/logo.PNG") is None
    assert detect_language("src/App.TSX").grammar == "tsx"


def test_deeply_nested_code_does_not_recurse():
    src = "const x = " + "[" * 3000 + "]" * 3000 + ";\nfunction f() { return 1; }\n"
    r = parse_file("deep.js", src)
    assert any(s.name == "f" for s in r.symbols)


def test_src_layout_is_not_part_of_the_module_path():
    from app.codeintel.parsers.python_parser import module_path_for

    assert module_path_for("src/flask/app.py") == "flask.app"
    assert module_path_for("src/flask/__init__.py") == "flask"
    assert module_path_for("src/tool.py") == "src.tool"  # a top-level src.py module dir is ambiguous; keep it
    assert module_path_for("pkg/src/x.py") == "pkg.src.x"
    r = parse_file("src/pkg/a.py", "from .b import helper\n\ndef main():\n    helper()\n")
    assert r.import_map["helper"] == "pkg.b.helper"
