import difflib
import json
from pathlib import Path
from ..models import ChangeSet, sha256
from ..governance.paths import safe_path, PolicyError
from ..persistence.artifacts import write_json, write_text

def current(path: Path):
    return path.read_text() if path.exists() else None

def content_hash(content):
    return sha256(content) if content is not None else None

def render(root: Path, proposal: ChangeSet):
    output = ""
    for change in proposal.changes:
        path = safe_path(root, change.path)
        before = current(path)
        output += "".join(difflib.unified_diff(
            (before or "").splitlines(True), (change.content or "").splitlines(True),
            fromfile="a/" + change.path if before is not None else "/dev/null",
            tofile="b/" + change.path if change.content is not None else "/dev/null"))
        # unified_diff separates lines but cannot encode EOF-newline state. Ensure
        # every file section ends before the next diff header, even for empty/new
        # files or sources without a final newline.
        if output and not output.endswith("\n"):
            output += "\n"
    return output

def apply(root: Path, directory: Path, proposal: ChangeSet):
    journal_path = directory / "operations.json"
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else {}
    # Prevalidate the entire proposal before the first mutation.
    for change in proposal.changes:
        path = safe_path(root, change.path)
        old = current(path)
        old_hash = content_hash(old)
        new_hash = content_hash(change.content)
        record = journal.get(change.path)
        replay = record and new_hash in record["permitted_hashes"] and old_hash == new_hash
        if old_hash != change.before_sha256 and not replay:
            raise PolicyError(f"Source changed since proposal: {change.path}")
    for change in proposal.changes:
        path = safe_path(root, change.path)
        old = current(path)
        record = journal.setdefault(change.path, {"original": old, "permitted_hashes": [content_hash(old)]})
        new_hash = content_hash(change.content)
        if new_hash not in record["permitted_hashes"]:
            record["permitted_hashes"].append(new_hash)
        # Durable journal precedes each mutation, allowing replay/recovery.
        write_json(journal_path, journal)
        if change.content is None:
            path.unlink(missing_ok=True)
        else:
            write_text(path, change.content)

def rollback(root: Path, directory: Path):
    journal_path = directory / "operations.json"
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else {}
    for name, record in journal.items():
        if content_hash(current(safe_path(root, name))) not in record["permitted_hashes"]:
            raise PolicyError(f"Rollback refused: external edits detected in {name}")
    for name, record in journal.items():
        path = safe_path(root, name)
        if record["original"] is None:
            path.unlink(missing_ok=True)
        else:
            write_text(path, record["original"])
    for name, record in journal.items():
        if current(safe_path(root, name)) != record["original"]:
            raise PolicyError("Rollback verification failed")
    return {"restored_files": sorted(journal), "verified": True}
