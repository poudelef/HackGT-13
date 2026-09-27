"""API errors. Shape: {"error": {"code", "message"}}."""

from __future__ import annotations


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra
