from pathlib import Path
import json
import pytest
from pydantic import ValidationError
from shortener_orchestrator.config import Settings
from shortener_orchestrator.models import Plan, ChangeSet, FileChange, sha256
from shortener_orchestrator.governance.paths import safe_path, allowed_change, PolicyError
from shortener_orchestrator.governance.policy import command, validate_changes
from shortener_orchestrator.governance.redaction import redact, sanitize
from shortener_orchestrator.tools.patches import apply, rollback, render

@pytest.mark.parametrize("path", ["../escape.java", "/etc/passwd", ".git/config", "src/../pom.xml",
                                  "src//main/Foo.java", "src\\main\\Foo.java"])
def test_path_escape_and_metadata_are_rejected(tmp_path, path):
    with pytest.raises(PolicyError):
        safe_path(tmp_path, path)

def test_symlink_escape_is_rejected(tmp_path):
    (tmp_path / "link").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(PolicyError):
        safe_path(tmp_path, "link/file.java")

@pytest.mark.parametrize("path", ["pom.xml", "mvnw", ".env", "src/main/resources/db/migration/V1__create_urls.sql",
                                  "src/main/resources/db/migration/V2__create_click_events.sql", "orchestrator/cli.py"])
def test_protected_files_are_rejected(path):
    with pytest.raises(PolicyError):
        allowed_change(path)

@pytest.mark.parametrize("profile", ["rm -rf /", "verify; curl evil", "mvn -DskipTests verify", "exec", "../verify"])
def test_only_named_command_profiles_are_allowed(profile):
    with pytest.raises(PolicyError):
        command(profile)

def test_verify_profile_runs_real_full_verification():
    assert command("verify") == ("mvn", "-B", "-ntp", "clean", "verify")

def test_plan_rejects_cycles_and_unknown_dependencies():
    for deps in [["a"], ["missing"]]:
        with pytest.raises(ValidationError):
            Plan(revision=1, tasks=[{"id": "a", "description": "work", "depends_on": deps, "files": ["docs/a.md"]}])

def test_secret_redaction():
    text = redact("password=hunter2 token=abc https://user:pass@example.com Authorization: Bearer xyz")
    for secret in ["hunter2", "abc", "user:pass", "xyz"]:
        assert secret not in text
    assert sanitize({"password": "value"})["password"] == "[REDACTED]"

def test_redaction_preserves_environment_reference_without_exposing_secret_defaults():
    assert redact("password: ${DB_PASSWORD}") == "password: ${DB_PASSWORD}"
    assert redact("token=${ACCESS_TOKEN}") == "token=${ACCESS_TOKEN}"
    assert "hidden" not in redact("password: ${DB_PASSWORD:hidden}")
    assert "literal-secret" not in redact("password=literal-secret")

def test_out_of_task_file_is_rejected():
    change = ChangeSet(summary="outside task", changes=[FileChange(path="docs/a.md", before_sha256=None, content="a")])
    with pytest.raises(PolicyError):
        validate_changes(change, ["docs/b.md"])

def test_patch_is_replay_safe_and_rollback_preserves_external_edits(tmp_path):
    root, artifacts = tmp_path / "workspace", tmp_path / "artifacts"
    root.mkdir()
    path = root / "docs/a.md"
    change = ChangeSet(summary="add", changes=[FileChange(path="docs/a.md", before_sha256=None, content="approved")])
    apply(root, artifacts, change)
    apply(root, artifacts, change)
    assert path.read_text() == "approved"
    path.write_text("human edit")
    with pytest.raises(PolicyError):
        rollback(root, artifacts)
    assert path.read_text() == "human edit"
    path.write_text("approved")
    assert rollback(root, artifacts)["verified"]
    assert not path.exists()

def test_patch_prevalidates_all_files_before_mutating(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "a.java").write_text("current")
    changes = ChangeSet(summary="invalid", changes=[
        FileChange(path="new.java", before_sha256=None, content="new"),
        FileChange(path="a.java", before_sha256=sha256("stale"), content="replacement")])
    with pytest.raises(PolicyError):
        apply(root, tmp_path / "artifacts", changes)
    assert not (root / "new.java").exists()

def test_render_separates_files_when_the_final_line_has_no_newline(service, tmp_path):
    from shortener_orchestrator.tools.repository import git
    run = service.start("brownfield")
    root = Path(run["workspace"])
    first = "docs/first.md"
    second = "docs/second.md"
    proposal = ChangeSet(summary="two files", changes=[
        FileChange(path=first, before_sha256=None, content="first line"),
        FileChange(path=second, before_sha256=None, content="second line\n")])
    patch = render(root, proposal)
    assert "first line\n--- /dev/null\n+++ b/docs/second.md" in patch
    patch_file = tmp_path / "multi-file.patch"
    patch_file.write_text(patch)
    git(root, "apply", "--check", str(patch_file))

def test_settings_cannot_escape_project_or_exceed_retry_limit(tmp_path):
    with pytest.raises(ValueError):
        Settings(repo=tmp_path, runtime_root=tmp_path.parent)
    with pytest.raises(ValueError):
        Settings(repo=tmp_path, max_retries=4)

def test_new_migration_versions_include_ten_but_exclude_baseline():
    allowed_change("src/main/resources/db/migration/V10__next_change.sql")
    allowed_change("src/main/resources/db/migration/V3__first_change.sql")
    with pytest.raises(PolicyError):
        allowed_change("src/main/resources/db/migration/V01__rewritten_baseline.sql")

def test_diff_covers_empty_and_large_added_files(service):
    from shortener_orchestrator.tools.repository import worktree_diff, inspect
    run = service.start("greenfield")
    root = Path(run["workspace"])
    empty = root / "docs/empty.md"
    empty.write_text("")
    before = worktree_diff(root)
    assert "docs/empty.md" in before
    empty.write_text("x" * 120000)
    assert worktree_diff(root) != before
    empty.write_text("x" * 1000001)
    with pytest.raises(PolicyError, match="fully reviewed"):
        worktree_diff(root)

def test_repository_context_includes_new_source_files(service):
    from shortener_orchestrator.tools.repository import inspect
    run = service.start("greenfield")
    root = Path(run["workspace"])
    name = "src/main/java/com/varun/shortener/NewFile.java"
    (root / name).write_text("// New source must be visible during repair\n")
    assert name in inspect(root)["files"]
