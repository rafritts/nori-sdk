"""Shared BeautifulSoup HTML-to-text parsing for WebClient and BrowserClient."""

from bs4 import BeautifulSoup

_STRIP_TAGS = [
    "script", "style", "nav", "header", "footer", "aside", "noscript", "svg", "iframe",
]
_MAX_CHARS = 8_000


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    # Also strip elements whose class suggests cookie banners / overlays
    for tag in soup.find_all(class_=lambda c: c and any(
        kw in " ".join(c).lower() for kw in ("cookie", "banner", "popup", "overlay", "gdpr")
    )):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)

    # Collapse runs of blank lines to a single blank line
    lines = text.splitlines()
    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = blank

    result = "\n".join(cleaned).strip()
    if len(result) > _MAX_CHARS:
        result = result[:_MAX_CHARS] + f"\n\n[truncated — {len(result)} chars total]"
    return result
