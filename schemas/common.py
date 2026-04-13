"""Shared Pydantic schemas used across the API."""

from typing import Any, Optional
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error envelope."""
    error: str
    message: str
    details: Optional[Any] = None
    correlation_id: Optional[str] = None

    model_config = {"json_schema_extra": {
        "example": {
            "error": "VALIDATION_ERROR",
            "message": "Invalid request body",
            "details": {"field": "email", "issue": "invalid email format"},
        }
    }}


class SuccessResponse(BaseModel):
    """Generic success message."""
    message: str
    data: Optional[Any] = None


class PaginationParams(BaseModel):
    """Common pagination query parameters."""
    page: int = 1
    per_page: int = 25
    sort_by: Optional[str] = None
    sort_dir: str = "asc"  # asc | desc

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


class PaginatedResponse(BaseModel):
    """Paginated list wrapper."""
    items: list[Any]
    total: int
    page: int
    per_page: int
    pages: int

    @classmethod
    def build(cls, items: list, total: int, params: PaginationParams) -> "PaginatedResponse":
        import math
        return cls(
            items=items,
            total=total,
            page=params.page,
            per_page=params.per_page,
            pages=math.ceil(total / params.per_page) if total > 0 else 0,
        )
