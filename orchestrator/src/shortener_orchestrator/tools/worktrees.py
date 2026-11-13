from pathlib import Path
from .repository import git
from ..governance.paths import PolicyError, validate_run_id

class Worktrees:
    def __init__(self, settings):
        self.settings = settings

    def create(self, run_id, baseline):
        validate_run_id(run_id)
        root = self.settings.home / "worktrees" / run_id
        root.parent.mkdir(parents=True, exist_ok=True)
        if root.exists():
            self.validate(root, baseline)
            return root
        # Detached worktrees retain the approved baseline and never merge or commit.
        git(self.settings.repo, "worktree", "add", "--detach", str(root), baseline)
        self.validate(root, baseline)
        return root

    def validate(self, root: Path, baseline: str):
        parent = self.settings.home / "worktrees"
        if root.is_symlink() or root.parent.resolve() != parent.resolve():
            raise PolicyError("Worktree is not owned by this orchestrator")
        common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()).resolve()
        if common != (self.settings.repo / ".git").resolve():
            raise PolicyError("Worktree belongs to another repository")
        if git(root, "rev-parse", "HEAD").strip() != baseline:
            raise PolicyError("Worktree baseline changed")
