"""Recoverable, operator-reviewed replacement of an unapplied patch."""
from pathlib import Path
from uuid import uuid4
import json
from ..models import ChangeSet, digest, sha256
from ..governance.paths import PolicyError
from ..governance.policy import validate_changes
from ..persistence.artifacts import write_json
from ..tools.repository import git
from ..tools.patches import content_hash, render
from . import gates
from .revisions import interrupts, check_workspace


def revise(service, run_id, request):
    proposal = ChangeSet.model_validate(request.get("proposal"))
    request = dict(request, proposal=proposal.model_dump())
    if (not request.get("actor", "").strip() or len(request["actor"]) > 100
            or not request.get("reason", "").strip() or len(request["reason"]) > 2000):
        raise PolicyError("Patch revision requires an actor and a reason")
    if len(json.dumps(request).encode()) > 500_000:
        raise PolicyError("Patch revision exceeds the size limit")
    with service.store.claim(run_id):
        if service.store.active_patch_revision(run_id):
            active = service.store.active_patch_revision(run_id)
            if digest(active["request"]) != digest(request):
                raise PolicyError("A different patch revision is pending recovery; use resume")
            return complete(service, run_id)
        run = service.store.get(run_id)
        if run["status"] != "AWAITING_APPROVAL" or run["stop"]:
            raise PolicyError("Run is not waiting at a revisable patch gate")
        state = dict(run["data"]["state"])
        graph = service.graph(state)
        config = {"configurable": {"thread_id": run_id}}
        snapshot = graph.get_state(config)
        waiting = interrupts(snapshot)
        if (len(waiting) != 1 or snapshot.next != ("patch_gate",)
                or waiting[0].get("action") != "patch"):
            raise PolicyError("Only a pending patch approval can be revised")
        old = waiting[0]
        if (old.get("approval_id") != request.get("approval_id")
                or old.get("proposal_hash") != request.get("proposal_hash")
                or service.store.approval_status(request["approval_id"]) != "pending"):
            raise PolicyError("Patch approval is stale, decided, or has the wrong hash")
        if state.get("applied_digest") or (service.store.directory(run_id) / "operations.json").exists():
            raise PolicyError("A patch can only be revised before any code is applied")
        pending = service.store.pending(run_id)
        if len(pending) != 1 or pending[0]["id"] != request["approval_id"]:
            raise PolicyError("Another approval is pending")
        check_workspace(service, state)
        allowed = [name for task in state["plan"]["tasks"] for name in task["files"]]
        validate_changes(proposal, allowed)
        if {change.path for change in proposal.changes} != set(allowed):
            raise PolicyError("Revised patch must cover every approved plan file exactly once")
        workspace = Path(state["workspace"])
        for change in proposal.changes:
            path = workspace / change.path
            actual = content_hash(path.read_text() if path.exists() else None)
            if change.before_sha256 != actual:
                raise PolicyError(f"Patch source hash does not match the clean worktree: {change.path}")
        if sha256(render(workspace, proposal)) == old["payload"]["patch_sha256"]:
            raise PolicyError("Revised patch contains no file-content changes")
        revision_id = uuid4().hex
        new_state = state | {"proposal": proposal.model_dump(), "status": "REVISING_PATCH"}
        service.store.begin_patch_revision(run_id, revision_id, request, new_state,
                                           snapshot.config["configurable"]["checkpoint_id"])
        return complete(service, run_id)


def complete(service, run_id):
    operation = service.store.active_patch_revision(run_id)
    if operation is None:
        raise PolicyError("No pending patch revision")
    if service.store.stopped(run_id):
        raise PolicyError("Run is stopped; explicit resume is required")
    state = operation["state"]
    check_workspace(service, state)
    graph = service.graph(state)
    config = {"configurable": {"thread_id": run_id}}
    snapshot = graph.get_state(config)
    if snapshot.values.get("proposal") != state["proposal"]:
        if snapshot.config["configurable"]["checkpoint_id"] != operation["checkpoint_id"]:
            raise PolicyError("Checkpoint changed outside the pending patch revision")
        graph.update_state(config, {"proposal": state["proposal"], "status": "REVISING_PATCH"},
                           as_node="consolidate")
        snapshot = graph.get_state(config)
    if snapshot.next != ("patch_gate",):
        raise PolicyError("Revised checkpoint will not execute only the patch gate")
    if not interrupts(snapshot):
        graph.invoke(None, config)
        snapshot = graph.get_state(config)
    waiting = interrupts(snapshot)
    if len(waiting) != 1 or waiting[0].get("action") != "patch":
        raise PolicyError("Revised patch did not pause at a new approval gate")
    new = waiting[0]
    if (new.get("approval_id") == operation["old_approval_id"]
            or service.store.approval_status(new["approval_id"]) != "pending"):
        raise PolicyError("Revised patch did not create a fresh pending approval")
    directory = service.store.directory(run_id)
    write_json(directory / "changes" / ("proposal-" + new["proposal_hash"][:16] + ".json"), state["proposal"])
    write_json(directory / "changes" / ("revision-" + operation["id"] + ".json"),
               {"request": operation["request"], "approval_id": new["approval_id"],
                "proposal_hash": new["proposal_hash"], "patch_sha256": new["payload"]["patch_sha256"]})
    service.store.finish_patch_revision(run_id, operation["id"], dict(snapshot.values), new["approval_id"],
        new["proposal_hash"], snapshot.config["configurable"]["checkpoint_id"])
    return service.inspect(run_id)
