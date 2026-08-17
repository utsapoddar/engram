from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib

LOCAL_CORPUS = "local"
CONFIG_NAME = "engram.toml"


@dataclass(frozen=True)
class Corpus:
    name: str
    path: Path
    include_pattern: str | None = None


def _default_root() -> Path:
    return Path(os.environ.get("ENGRAM_ROOT", Path.cwd())).expanduser()


def load_config(root: Path | None = None) -> tuple[Path, list[Corpus]]:
    """Resolve the canonical root and any declared read-only corpora."""
    local_root = Path(root).expanduser() if root is not None else _default_root()
    config_path = local_root / CONFIG_NAME
    if not config_path.is_file():
        return local_root, []
    data = tomllib.loads(config_path.read_text())
    external: list[Corpus] = []
    for name, entry in data.get("corpora", {}).items():
        if name == LOCAL_CORPUS:
            raise ValueError(
                f"corpus name {LOCAL_CORPUS!r} is reserved for the canonical store"
            )
        external.append(
            Corpus(
                name=name,
                path=Path(entry["path"]).expanduser(),
                include_pattern=entry.get("include_pattern"),
            )
        )
    return local_root, external
