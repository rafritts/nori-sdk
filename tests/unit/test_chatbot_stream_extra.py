"""response_filter extras must not re-stream already-sent turn content."""

from nori.chatbot import _stream_filter_extra


def test_suffix_only_when_filter_appends():
    base = "hey babyyy~"
    filtered = base + "\n\n![generated image](https://x/a.png)"
    assert _stream_filter_extra(base, filtered) == "\n\n![generated image](https://x/a.png)"


def test_no_extra_when_identical():
    base = "hello\n\n![generated image](https://x/a.png)"
    assert _stream_filter_extra(base, base) == ""


def test_rewrite_does_not_duplicate_prose():
    # Model put image first; filter reorders to text-then-image.
    base = "![generated image](https://x/a.png)\n\nhey babyyy~"
    filtered = "hey babyyy~\n\n![generated image](https://x/a.png)"
    assert _stream_filter_extra(base, filtered) == ""


def test_rewrite_emits_only_new_images():
    base = "hey"
    filtered = "hey there\n\n![generated image](https://x/a.png)\n\n![generated image](https://x/b.png)"
    # Body rewrote so we can't take a suffix; still inject images not in base.
    extra = _stream_filter_extra(base, filtered)
    assert "https://x/a.png" in extra
    assert "https://x/b.png" in extra
    assert "hey there" not in extra


def test_empty_base_returns_filtered():
    filtered = "only images\n\n![generated image](https://x/a.png)"
    assert _stream_filter_extra("", filtered) == filtered
