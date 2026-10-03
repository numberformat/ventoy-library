import json
import os
import warnings
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from .atomic import atomic_json
from .errors import LibraryError, SafetyError, StateError
from .metadata import STATE_DIRECTORY
from .models import AcquisitionMethod, ManagedImage, Release, VerificationStatus
from .safety import contained, destination, open_regular


class StateStore:
    def __init__(self, root: Path):
        self.root = destination(root)
        self.relative = Path(STATE_DIRECTORY) / "state.json"

    def _path(self, suffix: str = "") -> Path:
        return contained(self.root, str(self.relative) + suffix)

    def validate(self, image: ManagedImage) -> None:
        if not isinstance(image.relative_path, str):
            raise StateError("State paths must be strings.")
        parts = Path(image.relative_path).parts
        flat = len(parts) == 2 and parts == ("ISO", image.filename)
        legacy = (
            len(parts) == 4
            and parts[0] == "ISO"
            and parts[2] == image.provider
            and parts[3] == image.filename
        )
        if not (flat or legacy):
            raise StateError("State image is outside the supported ISO layout.")
        contained(self.root, image.relative_path)
        Release(
            image.provider,
            image.display_name,
            image.version,
            parts[1] if legacy else "flat",
            "unknown",
            image.filename,
            image.source_url,
            image.expected_size,
            image.checksum_algorithm,
            image.checksum,
        )
        status = VerificationStatus(image.verification_status)
        AcquisitionMethod(image.acquisition_method)
        if status == VerificationStatus.VERIFIED and image.checksum is None:
            raise StateError("Verified state requires a checksum.")
        if not isinstance(image.download_timestamp, str) or not image.download_timestamp:
            raise StateError("Missing acquisition timestamp.")

    def _read(self, path: Path) -> list[ManagedImage]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(data, dict)
            or type(data.get("schema_version")) is not int
            or data["schema_version"] != 1
        ):
            raise StateError("Unsupported state schema.")
        if not isinstance(data.get("images"), list):
            raise StateError("Invalid state image list.")
        images = [ManagedImage(**row) for row in data["images"]]
        seen = set()
        for image in images:
            try:
                self.validate(image)
            except SafetyError:
                raise  # Never fall back around a path-safety violation.
            except (LibraryError, ValueError, TypeError) as exc:
                raise StateError("Invalid state image metadata.") from exc
            if image.relative_path.casefold() in seen:
                raise StateError("Duplicate state path.")
            seen.add(image.relative_path.casefold())
        return images

    def load(self) -> list[ManagedImage]:
        path = self._path()
        if not path.exists() and not self._path(".bak").exists():
            return []
        try:
            return self._read(path)
        except (ValueError, TypeError, KeyError, StateError, FileNotFoundError) as exc:
            try:
                images = self._read(self._path(".bak"))
            except (ValueError, TypeError, KeyError, StateError, FileNotFoundError):
                raise StateError(
                    "State is corrupt; no valid backup. Refusing library changes."
                ) from exc
            warnings.warn("State is corrupt or missing; using previous valid backup.", stacklevel=2)
            return images

    def save(self, images: list[ManagedImage]) -> None:
        for image in images:
            self.validate(image)
        if len({i.relative_path.casefold() for i in images}) != len(images):
            raise StateError("Duplicate state path.")
        previous = self.load()
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() or self._path(".bak").exists():
            atomic_json(self._path(".bak"), self._encode(previous))
        atomic_json(path, self._encode(images))

    @staticmethod
    def _encode(images: list[ManagedImage]) -> dict:
        return {"schema_version": 1, "images": [asdict(i) for i in images]}

    @contextmanager
    def lock(self):
        """Single writer. Stale locks are deliberately never broken automatically."""
        path = contained(self.root, Path(STATE_DIRECTORY) / "write.lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = open_regular(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError as exc:
            raise StateError(
                "Library is locked. Check for another process or a stale lock."
            ) from exc
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(str(os.getpid()))
            yield
        finally:
            path.unlink()

    def remove_old(
        self, old: ManagedImage, replacement: ManagedImage, *, keep_old: bool = False
    ) -> None:
        if keep_old:
            return
        images = self.load()
        if old not in images or replacement not in images:
            raise SafetyError("Refusing to delete a file not tracked in state.")
        self.validate(old)
        self.validate(replacement)
        if old.provider != replacement.provider or old.relative_path == replacement.relative_path:
            raise SafetyError("Replacement must be a different file owned by the same provider.")
        from .verification import verify

        new_path = contained(self.root, replacement.relative_path)
        if not new_path.is_file():
            raise SafetyError("Replacement is missing.")
        verify(
            new_path,
            replacement.checksum_algorithm,
            replacement.checksum,
            replacement.expected_size,
        )
        path = contained(self.root, old.relative_path)
        if not path.is_file():
            raise SafetyError("Old image is not a regular file.")
        path.unlink()
        self.save([i for i in images if i != old])
