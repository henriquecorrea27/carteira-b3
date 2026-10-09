"""Notifier interface: the daily report is plain Markdown text split into channel-sized messages."""

from typing import Protocol


class NotifierError(Exception):
    """The channel rejected or did not receive the message (never includes secrets such as the URL)."""


class Notifier(Protocol):
    name: str
    max_length: int

    def send(self, messages: list[str]) -> None: ...


def split_message(text: str, limit: int) -> list[str]:
    """Splits on blank lines (sections), then on lines, and only cuts inside a line as a last resort."""
    chunks: list[str] = []
    current = ""

    def push(piece: str, sep: str) -> None:
        nonlocal current
        if not current:
            current = piece
        elif len(current) + len(sep) + len(piece) <= limit:
            current += sep + piece
        else:
            chunks.append(current)
            current = piece

    for block in text.strip().split("\n\n"):
        if len(block) <= limit:
            push(block, "\n\n")
            continue
        first = True
        for line in block.split("\n"):
            while len(line) > limit:
                push(line[:limit], "\n\n" if first else "\n")
                line, first = line[limit:], False
            push(line, "\n\n" if first else "\n")
            first = False
    if current:
        chunks.append(current)
    return chunks
