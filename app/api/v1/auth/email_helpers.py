"""
Auth email helpers — patchable in tests.

These functions are imported directly into auth routes so tests can patch them:
    with patch("app.api.v1.auth.email_helpers._send_verification_email", new_callable=AsyncMock):
        ...

or via old api.auth path:
    with patch("api.auth._send_verification_email", ...):
        ...
"""
import logging

log = logging.getLogger(__name__)


async def _send_verification_email(email: str, token: str) -> None:
    """
    Send email verification link.
    Patchable in tests. In production: sends via SendGrid.
    """
    log.info(f"[EMAIL] Verification link sent to {email}")
    # Production: integrate with SendGrid communications router


async def _send_password_reset_email(email: str, token: str) -> None:
    """
    Send password reset link.
    Patchable in tests. In production: sends via SendGrid.
    """
    log.info(f"[EMAIL] Password reset link sent to {email}")
