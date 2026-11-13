from pathlib import Path, PurePosixPath
import re

class PolicyError(RuntimeError):
    pass

def safe_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if not name or "\\" in name or relative.is_absolute() or ".." in relative.parts or "\x00" in name:
        raise PolicyError("Path must be a relative path without traversal")
    if str(relative) != name or any(part.startswith(".") for part in relative.parts):
        raise PolicyError("Hidden, noncanonical, or metadata paths are forbidden")
    candidate = root / name
    for parent in [candidate, *candidate.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise PolicyError("Symlinks are forbidden")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise PolicyError("Path escapes the workspace")
    return candidate

def allowed_change(name: str, deleting: bool = False):
    allowed = (
        name.startswith("src/main/java/com/varun/shortener/") and name.endswith(".java")
        or name.startswith("src/test/java/com/varun/shortener/") and name.endswith(".java")
        or re.fullmatch(r"src/main/resources/db/migration/V(?:[3-9]|[1-9][0-9]+)__[A-Za-z0-9_]+\.sql", name)
        or name == "src/main/resources/application.yml"
        or name.startswith("docs/") and name.endswith(".md")
    )
    if not allowed:
        raise PolicyError(f"Change outside approved source policy: {name}")

def validate_run_id(run_id: str):
    if not re.fullmatch(r"[a-f0-9]{12}", run_id):
        raise PolicyError("Invalid run ID")
