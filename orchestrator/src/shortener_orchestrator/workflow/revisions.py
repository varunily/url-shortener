"""Operator revisions of an undecided plan, with recoverable cross-database updates."""
from pathlib import Path
from uuid import uuid4
import json
from ..models import PlanRevisionRequest, digest
from ..governance.paths import PolicyError, safe_path
from ..governance.policy import validate_plan
from ..persistence.artifacts import write_json
from ..tools.repository import git
from .gates import plan_payload


def interrupts(snapshot):
    return [item.value for task in snapshot.tasks for item in task.interrupts]


def check_workspace(service, state):
    root = Path(state["workspace"])
    service.worktrees.validate(root, state["baseline"])
    if git(root, "status", "--porcelain", "--untracked-files=all").strip():
        raise PolicyError("Plan revision requires a clean worktree")
    for task in state["plan"]["tasks"]:
        for name in task["files"]:
            safe_path(root, name)


def revise(service, run_id, request):
    request = PlanRevisionRequest.model_validate(request)
    data = request.model_dump()
    if len(json.dumps(data).encode()) > 100_000:
        raise PolicyError("Plan revision exceeds the size limit")
    validate_plan(request.plan)
    with service.store.claim(run_id):
        active = service.store.active_plan_revision(run_id)
        if active:
            if digest(active["request"]) != digest(data):
                raise PolicyError("A different plan revision is pending recovery; use resume")
            return complete(service, run_id)
        run = service.store.get(run_id)
        if run["status"] != "AWAITING_APPROVAL" or run["stop"]:
            raise PolicyError("Run is not waiting for a revisable plan")
        state = run["data"]["state"]
        graph = service.graph(state)
        snapshot = graph.get_state({"configurable": {"thread_id": run_id}})
        waiting = interrupts(snapshot)
        if len(waiting) != 1 or snapshot.next != ("plan_gate",) or waiting[0].get("action") != "plan":
            raise PolicyError("Only an undecided plan gate can be revised")
        current = waiting[0]
        if (current["approval_id"] != request.approval_id or current["proposal_hash"] != request.proposal_hash
                or service.store.approval_status(request.approval_id) != "pending"):
            raise PolicyError("Plan approval is stale, decided, or has the wrong hash")
        state = dict(snapshot.values)
        if any(state.get(key) for key in ("completed_tasks", "pending_changes", "proposal", "applied_digest", "retry_count")):
            raise PolicyError("Plan revision is supported only before coding or patch application")
        if request.plan.revision != state["revision"] + 1:
            raise PolicyError("Revised plan must increment the current revision by exactly one")
        if digest(state["plan"] | {"revision": request.plan.revision}) == digest(data["plan"]):
            raise PolicyError("Revised plan must contain a substantive change")
        revision_id = uuid4().hex
        new_state = state | {"plan": data["plan"], "revision": request.plan.revision,
            "approval_granted": False, "status": "REVISING_PLAN",
            "plan_provenance": {"source": "operator_supplied_plan", "revision_id": revision_id,
                "actor": request.actor, "reason": request.reason, "previous_revision": state["revision"],
                "supersedes_approval_id": request.approval_id, "supersedes_proposal_hash": request.proposal_hash}}
        check_workspace(service, new_state)
        # Keep the exact original even if it predates versioned plan artifacts.
        directory = service.store.directory(run_id)
        old_path = directory / "plans" / f"{state['revision']}.json"
        if old_path.exists():
            if json.loads(old_path.read_text()) != state["plan"]:
                raise PolicyError("Original plan artifact differs from its checkpoint")
        else:
            write_json(old_path, state["plan"])
        service.store.begin_plan_revision(run_id, revision_id, data, new_state,
                                          snapshot.config["configurable"]["checkpoint_id"])
        return complete(service, run_id)


def complete(service, run_id):
    """Caller holds the run lock. Replaying this journal never invokes an agent."""
    operation = service.store.active_plan_revision(run_id)
    if operation is None:
        raise PolicyError("No pending plan revision")
    if service.store.stopped(run_id):
        raise PolicyError("Run is stopped; explicit resume is required")
    state = operation["state"]
    check_workspace(service, state)
    graph = service.graph(state)
    config = {"configurable": {"thread_id": run_id}}
    snapshot = graph.get_state(config)
    if snapshot.values.get("plan_provenance", {}).get("revision_id") != operation["id"]:
        if snapshot.config["configurable"]["checkpoint_id"] != operation["checkpoint_id"]:
            raise PolicyError("Checkpoint changed outside the pending revision")
        graph.update_state(config, {key: state[key] for key in
            ("plan", "revision", "approval_granted", "status", "plan_provenance")}, as_node="planning")
        snapshot = graph.get_state(config)
    if snapshot.values["plan"] != state["plan"] or snapshot.next != ("plan_gate",):
        raise PolicyError("Revised checkpoint does not match its journal")
    # An interrupt already present means a previous process reached the new gate.
    if not interrupts(snapshot):
        graph.invoke(None, config)
        snapshot = graph.get_state(config)
    waiting = interrupts(snapshot)
    payload = plan_payload(state)
    proposal_hash = digest(payload)
    approval_id = f"{run_id}:plan:{proposal_hash[:16]}"
    if (len(waiting) != 1 or waiting[0].get("action") != "plan"
            or waiting[0].get("approval_id") != approval_id or waiting[0].get("proposal_hash") != proposal_hash
            or waiting[0].get("payload") != payload or service.store.approval_status(approval_id) != "pending"):
        raise PolicyError("Revised plan did not pause at its new approval gate")
    directory = service.store.directory(run_id)
    versioned = directory / "plans" / f"{state['revision']}.json"
    if versioned.exists() and json.loads(versioned.read_text()) != state["plan"]:
        raise PolicyError("Revised plan artifact already exists with different content")
    write_json(versioned, state["plan"])
    write_json(directory / "plans" / f"{state['revision']}-operator-revision.json",
               {"request": operation["request"], "provenance": state["plan_provenance"],
                "approval_id": approval_id, "proposal_hash": proposal_hash})
    write_json(directory / "plan.json", state["plan"])
    service.store.finish_plan_revision(run_id, operation["id"], dict(snapshot.values), approval_id,
                                      proposal_hash, snapshot.config["configurable"]["checkpoint_id"])
    return service.inspect(run_id)
