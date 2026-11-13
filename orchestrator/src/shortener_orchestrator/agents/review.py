from pathlib import Path
from ..models import Review
from ..tools.repository import worktree_diff
from ..persistence.artifacts import write_json

def run(runtime, state):
    result = runtime.invoke(state, "review",
        lambda: runtime.provider.generate("review", Review, runtime.context(
            state, actual_diff=worktree_diff(Path(state["workspace"])))))
    write_json(runtime.store.directory(state["run_id"]) / "review.json", result.model_dump())
    return {"review": result.model_dump()}
