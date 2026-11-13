import time
from pathlib import Path
from ..tools.patches import rollback
from ..tools.repository import worktree_diff

def replan(runtime, state):
    retry = state["retry_count"] + 1
    if retry > runtime.settings.max_retries:
        raise ValueError("Retry limit exceeded")
    failure = {"test": state.get("test_result"), "review": state.get("review"),
               "static": state.get("static_result")}
    runtime.store.event(state["run_id"], "replanned",
        {"retry": retry, "previous_revision": state["revision"], "failure": failure},
        key=f"retry:{retry}")
    return {"retry_count": retry, "revision": state["revision"] + 1, "failure": failure,
            "recovery_started": state.get("recovery_started") or time.time(),
            "review": {}, "documentation": {}, "completed_tasks": [], "pending_changes": []}

def perform_rollback(runtime, state):
    runtime.check_stop(state)
    result = rollback(Path(state["workspace"]), runtime.store.directory(state["run_id"]))
    if worktree_diff(Path(state["workspace"])).strip():
        raise ValueError("Rollback left changes; operator inspection required")
    runtime.store.event(state["run_id"], "rolled_back", result, key="rollback")
    if state.get("recovery_started"):
        runtime.store.event(state["run_id"], "recovered",
            {"duration_seconds": time.time() - state["recovery_started"], "via": "rollback"}, key="recovered")
    return {"rollback_result": result, "status": "ROLLED_BACK"}
