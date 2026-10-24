"""Text derived from symbols: embedding summaries and full-text search tokens.

The same tokenizer is applied to indexed chunks and to queries, so keyword
search is symmetric: ``parseHTTPResponse``, ``parse_http_response`` and the
query "parse http response" all produce the tokens ``parse http response``
(plus the compound ``parsehttpresponse``).
"""

from __future__ import annotations

import re

from .parsers.base import Symbol

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*|[0-9]+")
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+[0-9]*|[A-Z]+[0-9]*|[0-9]+")
_IDENT_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

# Words that carry no retrieval signal in natural-language queries or
# docstrings. Kept small on purpose: identifiers like "get" or "set" matter.
STOPWORDS = frozenset(
    ["a", "an", "and", "are", "as", "at", "be", "by", "does", "do", "for", "from", "has", "have", "how", "i", "in", "into", "is", "it", "its", "me", "my", "of", "on", "or", "that", "the", "this", "to", "was", "what", "when", "where", "which", "who", "why", "will", "with", "you", "your", "can", "should", "would", "could", "there", "their", "them", "then", "than", "these", "those", "code", "function", "method", "class", "file", "implementation", "implement", "implemented", "self", "cls", "this", "def"]
)

MAX_SEARCH_TEXT_CHARS = 4000


def split_identifier(token: str) -> list[str]:
    """``getHTTPResponse_v2`` -> ``['get', 'http', 'response', 'v2']``."""
    parts: list[str] = []
    for piece in re.split(r"[_$\-]+", token):
        if not piece:
            continue
        sub = _CAMEL_RE.findall(piece)
        parts.extend(s.lower() for s in (sub or [piece]))
    return parts


def tokenize(text: str, *, drop_stopwords: bool = True) -> list[str]:
    """Lower-cased search tokens for arbitrary text (code or prose).

    Each identifier yields its parts plus the joined compound when it has
    more than one part.
    """
    out: list[str] = []
    for ident in _IDENT_RE.findall(text):
        parts = split_identifier(ident)
        if not parts:
            continue
        out.extend(parts)
        if len(parts) > 1:
            out.append("".join(parts))
    if drop_stopwords:
        out = [t for t in out if t not in STOPWORDS and len(t) > 1]
    return out


def query_terms(query: str) -> list[str]:
    """Distinct search terms for a user query, in order."""
    return list(dict.fromkeys(tokenize(query)))


def semantic_summary(sym: Symbol, *, language: str, path: str, module_name: str) -> str:
    '''The text that gets embedded for a chunk (not the raw source).

    Format::

        [python] pkg/auth.py :: TokenStore.issue
        def issue(self, user):
            """Issue a signed token."""
            calls: [_sign, encode]
    '''
    local_name = sym.qualified_name
    if module_name and local_name.startswith(module_name + "."):
        local_name = local_name[len(module_name) + 1 :]
    if sym.kind in ("module", "block"):
        header = f"[{language}] {path}"
    else:
        header = f"[{language}] {path} :: {local_name}"
    lines = [header, sym.signature] if sym.signature else [header]
    if sym.docstring:
        lines.append(f'    """{sym.docstring}"""')
    if sym.calls:
        lines.append(f"    calls: [{', '.join(sym.calls[:20])}]")
    return "\n".join(lines)


def search_text(sym: Symbol, *, path: str, imports: list[str] | None = None) -> str:
    """Weighted bag of tokens for PostgreSQL full-text search.

    Name tokens are repeated three times and path tokens twice so that
    ``ts_rank_cd`` favours a symbol named after the query over one that
    merely mentions it.
    """
    name_tokens = tokenize(sym.name, drop_stopwords=False)
    path_tokens = tokenize(path.replace("/", " ").replace(".", " "), drop_stopwords=False)
    body: list[str] = []
    body += tokenize(sym.signature)
    body += tokenize(sym.docstring)
    for call in sym.calls:
        body += tokenize(call, drop_stopwords=False)
    for ident in sym.identifiers:
        body += tokenize(ident, drop_stopwords=False)
    if sym.kind == "module" and imports:
        for imp in imports:
            body += tokenize(imp.replace("/", " ").replace(".", " "), drop_stopwords=False)
    parts = name_tokens * 3 + path_tokens * 2 + list(dict.fromkeys(body))
    text = " ".join(parts)
    return text[:MAX_SEARCH_TEXT_CHARS]


def tsquery_from_terms(terms: list[str]) -> str:
    """OR-query for to_tsquery('simple', …). Terms are already sanitised."""
    safe = [t for t in terms if re.fullmatch(r"[a-z0-9]+", t)]
    return " | ".join(safe)
