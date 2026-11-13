from pathlib import Path
from ..models import sha256
from ..tools.repository import worktree_diff
from ..persistence.artifacts import write_json

def run(runtime, state):
    def execute():
        root = Path(state["workspace"])
        before = sha256(worktree_diff(root))
        if before != state["applied_digest"]:
            raise ValueError("Workspace changed before testing")
        result = runtime.runner.run(state["run_id"], root, state["revision"])
        if sha256(worktree_diff(root)) != before:
            result.passed = False
            result.classification = "workspace_changed"
        return result
    result = runtime.invoke(state, "testing", execute)
    # A completed command with failing tests is an agent failure, not success.
    if not result.passed:
        runtime.store.event(state["run_id"], "validation_failed", result.model_dump())
    write_json(runtime.store.directory(state["run_id"]) / "tests" / f"{state['revision']}.json", result.model_dump())
    return {"test_result": result.model_dump()}
