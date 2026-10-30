"""Small deterministic normalization helpers shared by source adapters."""

from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = frozenset({"gh_src", "source", "ref", "referrer"})


class _TextExtractor(HTMLParser):
    """Collect readable text while ignoring markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        stripped = " ".join(data.split())
        if stripped:
            self.parts.append(stripped)


def normalize_optional_text(value: str | None) -> str | None:
    """Collapse whitespace and turn blank optional strings into nulls."""
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def html_to_text(value: str | None) -> str | None:
    """Convert Greenhouse's entity-encoded HTML into stable readable text."""
    if value is None:
        return None

    decoded = value
    for _ in range(2):
        next_value = unescape(decoded)
        if next_value == decoded:
            break
        decoded = next_value

    parser = _TextExtractor()
    parser.feed(decoded)
    parser.close()
    return normalize_optional_text(" ".join(parser.parts))


def canonicalize_apply_url(value: str) -> str:
    """Remove fragments and known tracking parameters without dropping job IDs."""
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("apply URL must be an absolute HTTP(S) URL")

    kept_query = [
        (key, query_value)
        for key, query_value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
        and not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]
    normalized_path = parsed.path or "/"
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path.rstrip("/") or "/",
            urlencode(sorted(kept_query)),
            "",
        )
    )
