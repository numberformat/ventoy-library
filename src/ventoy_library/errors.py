class LibraryError(Exception):
    """An expected, user-facing failure."""


class SafetyError(LibraryError):
    """An operation cannot be performed safely."""


class StateError(LibraryError):
    """The state database cannot be trusted."""
