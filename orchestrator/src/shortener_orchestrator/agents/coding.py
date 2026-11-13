from ..models import ChangeSet
from ..governance.policy import validate_changes
from ..persistence.artifacts import write_json
from ..governance.paths import PolicyError
from uuid import uuid4

def run(runtime, state):
    task = next(task for task in state["plan"]["tasks"] if task["id"] == state["task_id"])
    attempts = sum(event["kind"] == "agent_started" and event["data"].get("agent") == "coding"
                   and event["data"].get("task_id") == task["id"]
                   and event["data"].get("revision") == state["revision"]
                   for event in runtime.store.events(state["run_id"]))
    if attempts >= 4:
        raise PolicyError("Coding task exhausted its initial attempt plus three retries")
    context = runtime.context(state, task=task, proposed_dependencies=state.get("pending_changes", []))
    context["coding_feedback"] = state.get("coding_feedback", {}).get(task["id"], "")
    directory = runtime.store.directory(state["run_id"]) / "proposals"
    def propose_and_validate():
        proposal = runtime.provider.generate("coding", ChangeSet, context)
        write_json(directory / f"{state['revision']}-{task['id']}-attempt-{uuid4().hex[:12]}.json",
                   proposal.model_dump())
        validate_changes(proposal, task["files"])
        if {change.path for change in proposal.changes} != set(task["files"]):
            raise PolicyError("Proposal must cover every approved task file exactly once")
        for change in proposal.changes:
            expected = context["repository"]["files"].get(change.path, {}).get("sha256")
            if change.before_sha256 != expected:
                raise PolicyError(f"Proposal source hash does not match the inspected file: {change.path}")
        return proposal
    proposal = runtime.invoke(state, "coding", propose_and_validate)
    write_json(directory / f"{state['revision']}-{task['id']}.json", proposal.model_dump())
    return {"task_proposal": proposal.model_dump()}
