"""Current output names and read-only compatibility with pre-rename files."""
from pathlib import Path


MANIFEST_EXTS = (".misong.json", ".nde.json")
SPLIT_EXTS = (".misongsplit.json", ".ndesplit.json")
TASK_NAMES = ("misong-task.json", "nde-task.json")


def find_sidecar(base: Path, extensions: tuple[str, ...]) -> Path | None:
    """Prefer the current name; consult the legacy name only when it is absent."""
    base = Path(base)
    return next((path for ext in extensions
                 if (path := base.with_name(base.name + ext)).is_file()), None)
