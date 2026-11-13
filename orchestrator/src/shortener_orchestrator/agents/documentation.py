from pathlib import Path
from ..models import Documentation
from ..tools.repository import worktree_diff
from ..persistence.artifacts import write_json

def run(runtime, state):
    result = runtime.invoke(state, "documentation",
        lambda: runtime.provider.generate("documentation", Documentation, runtime.context(
            state, actual_diff=worktree_diff(Path(state["workspace"])))))
    write_json(runtime.store.directory(state["run_id"]) / "documentation.json", result.model_dump())
    return {"documentation": result.model_dump()}
