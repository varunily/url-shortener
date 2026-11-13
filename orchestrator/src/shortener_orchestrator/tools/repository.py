from pathlib import Path
import subprocess
from ..governance.paths import PolicyError, safe_path
from ..governance.redaction import redact
from ..models import sha256

def git(repo: Path, *args: str, timeout=30) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], shell=False, text=True,
                            capture_output=True, timeout=timeout)
    if result.returncode:
        raise PolicyError(redact(result.stderr.strip() or "Git operation failed"))
    return result.stdout

def baseline(repo: Path):
    return git(repo, "rev-parse", "--verify", "HEAD").strip()

def inspect(root: Path) -> dict:
    paths = git(root, "ls-files", "-z").split("\0")
    paths += git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    files = {}
    total = 0
    for name in paths:
        if not name or not (name.startswith("src/") or name == "pom.xml"):
            continue
        path = safe_path(root, name)
        if not path.exists():
            files[name] = {"sha256": None, "content": None, "deleted": True}
            continue
        if not path.is_file():
            raise PolicyError("Source tree contains a non-file")
        raw = path.read_bytes()
        if len(raw) > 100_000:
            continue
        total += len(raw)
        if total > 500_000:
            break
        files[name] = {"sha256": sha256(raw), "content": redact(raw.decode("utf-8"))}
    return {"files": files, "baseline": baseline(root)}

def worktree_diff(root: Path):
    diff = git(root, "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--")
    for name in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if name:
            path = safe_path(root, name)
            if not path.is_file() or path.stat().st_size > 1_000_000:
                raise PolicyError("Untracked file cannot be fully reviewed: " + name)
            import difflib
            raw = path.read_bytes()
            mode = "100755" if path.stat().st_mode & 0o111 else "100644"
            # Include filename, mode, and raw hash even for an empty/new file.
            diff += f"diff --git a/{name} b/{name}\nnew file mode {mode}\nsha256 {sha256(raw)}\n"
            diff += "".join(difflib.unified_diff([], raw.decode("utf-8").splitlines(True),
                                                 fromfile="/dev/null", tofile="b/" + name))
    return diff
