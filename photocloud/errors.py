"""Exceptions whose messages are safe to show to the user."""


class SourceError(Exception):
    """A photo source cannot be used; the message is shown in the settings panel."""


class AuthRequired(SourceError):
    """The source needs the user to connect an account first."""

    def __init__(self, provider: str, message: str | None = None) -> None:
        super().__init__(message or "Connect your account first.")
        self.provider = provider
