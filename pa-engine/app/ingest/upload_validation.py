"""PDF magic bytes, size, and a text layer. Scanned files are refused."""

from __future__ import annotations

from app.errors import ApiError

MAX_BYTES = 20_000_000


def validate_bytes(data: bytes) -> None:
    if not data.startswith(b"%PDF"):
        raise ApiError("INVALID_PDF", "The file is not a PDF.", 400)
    if len(data) > MAX_BYTES:
        raise ApiError("INVALID_PDF", "The PDF is larger than 20 MB.", 400)
    if len(data) < 8:
        raise ApiError("INVALID_PDF", "The PDF is empty.", 400)


def require_text_layer(pages: list[dict]) -> None:
    if not pages or not any((page.get("text") or "").strip() for page in pages):
        raise ApiError(
            "NO_TEXT_LAYER",
            "This PDF has no text layer. A scanned image cannot be read.",
            400,
        )
