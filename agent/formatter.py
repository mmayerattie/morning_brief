"""
Converts Claude's markdown output to Telegram-compatible HTML.

Telegram supports only: <b>, <i>, <code>, <pre>, <a href="...">.
It does NOT support standard markdown (**bold**, # headers, - lists).
Messages over 4096 chars must be split — we split on paragraph boundaries
to keep the reading experience intact.
"""

import re

TELEGRAM_MAX_CHARS = 4096


def to_telegram_html(text: str) -> str:
    """Convert markdown text to Telegram HTML."""
    # Escape HTML special chars first (order matters: & must be first)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")

    # **bold** → <b>bold</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # *italic* → <i>italic</i>  (single asterisk, not double)
    text = re.sub(r"\*([^*\n]+?)\*", r"<i>\1</i>", text)

    # `code` → <code>code</code>
    text = re.sub(r"`([^`\n]+?)`", r"<code>\1</code>", text)

    # [link text](url) → <a href="url">link text</a>
    text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2">\1</a>', text)

    # ## Header → <b>Header</b>  (markdown headers become bold lines)
    text = re.sub(r"^#{1,3}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    return text.strip()


def split_into_chunks(text: str) -> list[str]:
    """
    Split text into chunks that fit within Telegram's 4096-char limit.
    Splits on double newlines (paragraph boundaries) to avoid mid-sentence cuts.
    """
    if len(text) <= TELEGRAM_MAX_CHARS:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        candidate = (current + "\n\n" + para).strip() if current else para
        if len(candidate) <= TELEGRAM_MAX_CHARS:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # If a single paragraph exceeds the limit, hard-split it
            if len(para) > TELEGRAM_MAX_CHARS:
                for i in range(0, len(para), TELEGRAM_MAX_CHARS):
                    chunks.append(para[i : i + TELEGRAM_MAX_CHARS])
                current = ""
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks


def format_for_telegram(markdown_text: str) -> list[str]:
    """Full pipeline: convert markdown → Telegram HTML, then split if needed."""
    html = to_telegram_html(markdown_text)
    return split_into_chunks(html)
