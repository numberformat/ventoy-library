"""Runtime project identity. Keep packaging URLs synchronized with these constants."""

__version__ = "0.1.0"
PROJECT_NAME = "ventoy-library"
REPOSITORY = "numberformat/ventoy-library"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
GIT_SOURCE = f"git+{REPOSITORY_URL}.git"
STATE_DIRECTORY = f".{PROJECT_NAME}"
USER_AGENT = f"{PROJECT_NAME}/{__version__} (+{REPOSITORY_URL})"
