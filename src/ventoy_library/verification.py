import hashlib
import hmac
import os
from pathlib import Path

from .errors import LibraryError
from .models import VerificationStatus
from .safety import open_regular


def verify(
    path: Path, algorithm: str | None, checksum: str | None, size: int | None = None
) -> VerificationStatus:
    with os.fdopen(open_regular(path, os.O_RDONLY), "rb") as stream:
        if size is not None and os.fstat(stream.fileno()).st_size != size:
            raise LibraryError("Image size mismatch.")
        if algorithm is None and checksum is None:
            return VerificationStatus.UNVERIFIED
        if algorithm not in {"sha256", "sha512"} or not checksum:
            raise LibraryError("Missing checksum or unsupported checksum algorithm.")
        digest = hashlib.file_digest(stream, algorithm).hexdigest()
    if not hmac.compare_digest(digest.lower(), checksum.lower()):
        raise LibraryError("Checksum mismatch; previous image has been preserved.")
    return VerificationStatus.VERIFIED
