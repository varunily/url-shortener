from ..models import ChangeSet

def next_task(state):
    completed = set(state["completed_tasks"])
    for task in state["plan"]["tasks"]:
        if task["id"] not in completed and set(task["depends_on"]) <= completed:
            return {"task_id": task["id"]}
    if len(completed) != len(state["plan"]["tasks"]):
        raise ValueError("Task graph cannot make progress")
    return {"task_id": ""}

def collect(state):
    pending = {change["path"]: change for change in state.get("pending_changes", [])}
    for change in state["task_proposal"]["changes"]:
        # Overlapping tasks must carry forward the initial source hash.
        if change["path"] in pending:
            change = dict(change, before_sha256=pending[change["path"]]["before_sha256"])
        pending[change["path"]] = change
    return {"pending_changes": list(pending.values()),
            "completed_tasks": state["completed_tasks"] + [state["task_id"]]}

def consolidate(state):
    proposal = ChangeSet(summary=f"Plan revision {state['revision']}", changes=state["pending_changes"])
    return {"proposal": proposal.model_dump()}
