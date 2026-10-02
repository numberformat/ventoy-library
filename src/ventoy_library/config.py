import json
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, Decimal, DecimalException
from pathlib import Path

from platformdirs import user_config_path

from .atomic import atomic_json
from .errors import LibraryError
from .metadata import PROJECT_NAME
from .safety import destination


@dataclass(frozen=True)
class Config:
    destination: str | None = None
    safety_margin: int = 2 * 1024**3
    destination_mode: str = "ventoy"
    release_catalog: str | None = None

    def __post_init__(self):
        if self.destination_mode not in {"ventoy", "directory"}:
            raise LibraryError("Destination mode must be ventoy or directory.")
        if self.destination is not None and not isinstance(self.destination, str):
            raise LibraryError("Configured destination must be a path string.")
        if self.release_catalog is not None and not isinstance(self.release_catalog, str):
            raise LibraryError("Release catalog must be a path string.")
        if type(self.safety_margin) is not int or self.safety_margin < 0:
            raise LibraryError("Safety margin must be a nonnegative integer in bytes.")


def config_path() -> Path:
    return user_config_path(PROJECT_NAME, appauthor=False) / "config.json"


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    try:
        return Config(**json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return Config()
    except (ValueError, TypeError) as exc:
        raise LibraryError(f"Invalid configuration: {path}") from exc


def set_value(key: str, value: str, path: Path | None = None) -> Config:
    path = path or config_path()
    data = asdict(load(path))
    if key == "destination":
        data[key] = str(destination(value))
    elif key == "release_catalog":
        data[key] = str(Path(value).expanduser().absolute())
        from .release_catalog import load_catalog

        load_catalog(Path(data[key]))
    elif key == "destination_mode":
        data[key] = value
    elif key == "safety_margin":
        try:
            gib = Decimal(value)
            if not gib.is_finite() or gib < 0:
                raise ValueError("Invalid GiB amount")
            data[key] = int((gib * 1024**3).to_integral_value(rounding=ROUND_CEILING))
        except (DecimalException, ValueError, OverflowError) as exc:
            raise LibraryError("Safety margin must be a nonnegative number in GiB.") from exc
    else:
        raise LibraryError(f"Unknown configuration key: {key}")
    config = Config(**data)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, asdict(config))
    return config
