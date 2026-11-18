"""Whether this installation can send email (DEC-0041).

An installation runs before its email account is set up. Auth then has no SMTP host and
would accept an invitation or a recovery request without sending anything, so every action
that needs an email stops here first with ``email_not_configured``.
"""

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.systems.access.users.coordination import InvitationError

CODE = "email_not_configured"
MESSAGE = "Email is not set up yet. Set it up in Slate Operations settings on the server PC."


class EmailNotConfigured(InvitationError):
    """The action needs an email, and email is not set up."""


def email_configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_port and settings.smtp_admin_email)


def require_email_configured() -> None:
    if not email_configured():
        raise EmailNotConfigured(MESSAGE)


def email_not_configured() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": CODE, "message": MESSAGE},
    )
