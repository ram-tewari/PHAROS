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


#: Kinds whose own lines are the code a question is about. Containers
#: (classes, impls, modules) would only repeat the members indexed after them.
BODY_KINDS = frozenset({"function", "method", "macro", "block"})
#: Body lines in the embedded summary (0 = signature, docstring and calls only).
SUMMARY_BODY_LINES = 25
SUMMARY_BODY_CHARS = 1200
_DOCSTRING_RE = re.compile(r'^\s*[rbuRBU]?("""|\'\'\')(.|\n)*?\1', re.S)


def body_excerpt(lines: list[str], sym: Symbol, *, max_lines: int | None = None,
                 max_chars: int = SUMMARY_BODY_CHARS) -> str:
    """The first non-blank lines of a function after its signature (docstring removed).

    Behaviour that lives only in the body ("run the persistent pre-run hooks")
    is invisible to a summary of signature and docstring alone.
    """
    max_lines = SUMMARY_BODY_LINES if max_lines is None else max_lines
    if max_lines <= 0 or sym.kind not in BODY_KINDS:
        return ""
    body = lines[sym.start_line - 1:sym.end_line]
    if sym.kind != "block":
        body = _after_signature(body, sym.signature)
    text = _DOCSTRING_RE.sub("", "\n".join(body), count=1) if sym.docstring else "\n".join(body)
    kept = [line.rstrip() for line in text.splitlines() if line.strip() and not _BRACES_ONLY.match(line)]
    return "\n".join(kept[:max_lines])[:max_chars]


_BRACES_ONLY = re.compile(r"^\s*[{}()\[\];,]*\s*$")
_SPACE = re.compile(r"\s+")


def _after_signature(body: list[str], signature: str) -> list[str]:
    """Drop decorator lines and the lines the (whitespace-collapsed) signature spans."""
    i = 0
    while i < len(body) and body[i].lstrip().startswith("@") and not signature.lstrip().startswith("@"):
        i += 1
    need = len(_SPACE.sub("", signature)) if signature else 1
    seen = 0
    while i < len(body) and seen < need:
        seen += len(_SPACE.sub("", body[i])) or 0
        i += 1
    return body[i:]


def with_description(summary: str, description: str) -> str:
    """Insert ``purpose: <description>`` after the summary's signature and
    docstring, ahead of the body excerpt (embedders truncate long inputs)."""
    lines = summary.split("\n")
    at = 2 if len(lines) > 1 and " :: " in lines[0] else 1  # after the signature, or the header of a block
    if len(lines) > at and lines[at].startswith('    """'):
        at += 1
    return "\n".join([*lines[:at], f"    purpose: {description}", *lines[at:]])


def semantic_summary(sym: Symbol, *, language: str, path: str, module_name: str, body: str = "",
                     description: str = "") -> str:
    '''The text that gets embedded for a chunk (not the raw source).

    Format::

        [python] pkg/auth.py :: TokenStore.issue
        def issue(self, user):
            """Issue a signed token."""
            payload = {"sub": user.id}
            return self._sign(encode(payload))
            calls: [_sign, encode]

    ``body`` (see :func:`body_excerpt`) goes before the call list: embedders
    truncate long inputs (MiniLM at 256 tokens), and the body says more.
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
    if description:
        lines.append(f"    purpose: {description}")
    if body:
        lines.append(body)
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
