"""Dispute API module."""


def get_router():
    """Lazy import router to avoid FastAPI import at module load time."""
    from app.api.disputes.routes import router  # noqa: PLC0415
    return router


__all__ = ["get_router"]
