from __future__ import annotations

# keep [ and ] (they form masked-link syntax [text](url)); ( ) alone are inert and
# appear in ~22% of catalog names like "Vow (Chastity)", so leave them intact
_MARKDOWN_CHARS = frozenset('*_~`|>[]\\')

_MENTION_CHARS = frozenset('@<>#')


def sanitize_name(name: str) -> str:
    return "".join(
        ch for ch in name if ch not in _MARKDOWN_CHARS and ch not in _MENTION_CHARS
    ).strip()
