import re
from html import escape


def markdown_to_html(message: str) -> str:
    lines = (message or "").replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    paragraph: list[str] = []
    items: list[str] = []
    ordered = False

    def inline(text: str) -> str:
        safe = escape(text)
        safe = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+|/[^\s)]+|mailto:[^\s)]+)\)", r'<a href="\2">\1</a>', safe)
        safe = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", safe)
        safe = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", safe)
        safe = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", safe)
        safe = re.sub(r"_([^_]+)_", r"<em>\1</em>", safe)
        safe = re.sub(r"`([^`]+)`", r"<code>\1</code>", safe)
        return safe

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(f"<p>{'<br/>'.join(inline(line) for line in paragraph)}</p>")
            paragraph = []

    def flush_items() -> None:
        nonlocal items, ordered
        if items:
            tag = "ol" if ordered else "ul"
            blocks.append(f"<{tag}>{''.join(f'<li>{inline(item)}</li>' for item in items)}</{tag}>")
            items = []
            ordered = False

    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            flush_paragraph()
            flush_items()
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", trimmed)
        if heading:
            flush_paragraph()
            flush_items()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", trimmed)
        numbered = re.match(r"^\d+\.\s+(.+)$", trimmed)
        if bullet or numbered:
            flush_paragraph()
            next_ordered = numbered is not None
            if items and ordered != next_ordered:
                flush_items()
            ordered = next_ordered
            items.append((bullet or numbered).group(1))
            continue

        flush_items()
        paragraph.append(line)

    flush_paragraph()
    flush_items()
    return "".join(blocks)


def sanitize_rich_html(message: str) -> str:
    html = message or ""
    html = re.sub(r"<\s*(script|style|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>", "", html, flags=re.I | re.S)
    html = re.sub(r"\s+on[a-z]+\s*=\s*(['\"]).*?\1", "", html, flags=re.I | re.S)
    html = re.sub(r"\s+on[a-z]+\s*=\s*[^\s>]+", "", html, flags=re.I)
    html = re.sub(r"(href|src)\s*=\s*(['\"])\s*javascript:.*?\2", r'\1="#"', html, flags=re.I | re.S)
    return html


def message_to_html(message: str, content_format: str) -> str:
    if content_format == "rich_text":
        return sanitize_rich_html(message)
    if content_format == "markdown":
        if re.search(r"</?(h[1-4]|p|ul|ol|li|strong|b|em|i|a|blockquote|br|hr|code|pre)\b", message or "", flags=re.I):
            return sanitize_rich_html(message)
        return sanitize_rich_html(markdown_to_html(message))
    return escape(message or "").replace("\n", "<br/>")
