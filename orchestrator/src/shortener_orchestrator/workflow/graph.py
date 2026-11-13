from pathlib import Path
import time
from langgraph.graph import StateGraph, START, END
from .state import WorkflowState
from . import gates, scheduling, recovery
from ..agents import requirement, planning, coding, testing, review, documentation
from ..models import ChangeSet, sha256, digest
from ..governance.policy import validate_changes
from ..governance.paths import allowed_change, PolicyError
from ..tools.patches import render, apply
from ..tools.repository import worktree_diff, git
from ..persistence.artifacts import write_text

def build_graph(runtime, checkpointer):
    graph = StateGraph(WorkflowState)
    for name, module in [("requirements", requirement), ("planning", planning), ("coding", coding),
                         ("testing", testing), ("review", review), ("documentation", documentation)]:
        graph.add_node(name, lambda state, module=module: module.run(runtime, state))
    graph.add_node("clarification", lambda state: gates.clarify(runtime, state))
    graph.add_node("plan_gate", lambda state: gates.approval(runtime, state, "plan",
        gates.plan_payload(state)))
    graph.add_node("select_task", scheduling.next_task)
    graph.add_node("collect", scheduling.collect)
    graph.add_node("consolidate", scheduling.consolidate)

    def patch_gate(state):
        proposal = ChangeSet.model_validate(state["proposal"])
        permitted = [name for task in state["plan"]["tasks"] for name in task["files"]]
        policy = validate_changes(proposal, permitted)
        directory = runtime.store.directory(state["run_id"])
        path = directory / "changes" / f"{state['revision']}-{digest(proposal.model_dump())[:16]}.patch"
        patch = render(Path(state["workspace"]), proposal)
        write_text(path, patch)
        return gates.approval(runtime, state, "patch",
            {"revision": state["revision"], "patch": str(path), "patch_sha256": sha256(patch),
             "files": [change.path for change in proposal.changes], "policy": policy})

    def apply_changes(state):
        runtime.check_stop(state)
        proposal = ChangeSet.model_validate(state["proposal"])
        apply(Path(state["workspace"]), runtime.store.directory(state["run_id"]), proposal)
        actual = worktree_diff(Path(state["workspace"]))
        write_text(runtime.store.directory(state["run_id"]) / "changes" / "actual.patch", actual)
        runtime.store.event(state["run_id"], "changes_applied",
            {"revision": state["revision"], "files": [change.path for change in proposal.changes],
             "diff_sha256": sha256(actual)}, key=f"apply:{state['revision']}")
        return {"applied_digest": sha256(actual), "status": "VALIDATING"}

    def static_checks(state):
        runtime.check_stop(state)
        runtime.store.event(state["run_id"], "static_started", {"revision": state["revision"]})
        root = Path(state["workspace"])
        findings = []
        try:
            changed = git(root, "diff", "--name-only", "HEAD").splitlines()
            changed += [p for p in git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if p]
            for name in changed:
                allowed_change(name)
            if sha256(worktree_diff(root)) != state["applied_digest"]:
                findings.append("Workspace changed after approved patch application")
        except PolicyError as error:
            findings.append(str(error))
        result = {"passed": not findings, "findings": findings}
        runtime.store.event(state["run_id"], "static_finished", result)
        return {"static_result": result}

    def validation_barrier(state):
        runtime.store.event(state["run_id"], "validation_barrier",
            {"tests_passed": state["test_result"]["passed"], "static_passed": state["static_result"]["passed"]},
            key=f"validation:{state['revision']}")
        if state["test_result"]["passed"] and state["static_result"]["passed"]:
            if state.get("recovery_started"):
                runtime.store.event(state["run_id"], "recovered",
                    {"duration_seconds": time.time() - state["recovery_started"], "via": "validation"}, key="recovered")
            return {}
        return {"recovery_started": state.get("recovery_started") or time.time()}

    def validation_route(state):
        if state["test_result"]["passed"] and state["static_result"]["passed"]:
            return "review_and_document"
        if state["test_result"]["classification"] in {"environment", "timeout", "output_limit", "workspace_changed", "stopped"} \
                or not state["static_result"]["passed"]:
            return "safe_stop"
        return "replan" if state["retry_count"] < runtime.settings.max_retries else "rollback_gate"

    def final_gate(state):
        if sha256(worktree_diff(Path(state["workspace"]))) != state["applied_digest"]:
            raise PolicyError("Source changed after validation; readiness approval is invalid")
        return gates.approval(runtime, state, "release",
            {"diff_sha256": state["applied_digest"], "tests": state["test_result"],
             "review": state["review"], "documentation": state["documentation"],
             "merges_or_deploys": False})

    def report(state):
        runtime.check_stop(state)
        result = state["test_result"]
        text = ("# Release readiness\n\n"
                f"Run: {state['run_id']}\n\nProvider: {state['provider']} / {state['model']}\n\n"
                f"Baseline: {state['baseline']}\n\nApproved diff: {state['applied_digest']}\n\n"
                f"Tests executed: {result['unit_tests']} unit/HTTP, {result['integration_tests']} PostgreSQL integration; "
                f"{result['failures']} failures, {result['errors']} errors, {result['skipped']} skipped.\n\n"
                + state["documentation"]["summary"] + "\n\nReview: " + state["review"]["summary"]
                + "\n\nChanges remain in the isolated worktree. No merge, commit, or deployment performed by this workflow.\n")
        write_text(runtime.store.directory(state["run_id"]) / "release-readiness.md", text)
        runtime.store.event(state["run_id"], "release_ready", {"diff_sha256": state["applied_digest"]}, key="release_ready")
        return {"status": "READY"}

    def rejected_route(state):
        if state["approval_granted"]:
            return "approved"
        if (runtime.store.directory(state["run_id"]) / "operations.json").exists():
            return "rollback_gate"
        return "rejected"

    graph.add_node("patch_gate", patch_gate)
    graph.add_node("apply", apply_changes)
    graph.add_node("static_checks", static_checks)
    graph.add_node("validation_barrier", validation_barrier)
    graph.add_node("review_and_document", lambda state: {})
    graph.add_node("review_barrier", lambda state: {})
    graph.add_node("replan", lambda state: recovery.replan(runtime, state))
    graph.add_node("rollback_gate", lambda state: gates.approval(runtime, state, "rollback",
        {"baseline": state["baseline"], "workspace": state["workspace"],
         "retry_count": state["retry_count"],
         "journal": str(runtime.store.directory(state["run_id"]) / "operations.json")}))
    graph.add_node("rollback", lambda state: recovery.perform_rollback(runtime, state))
    graph.add_node("final_gate", final_gate)
    graph.add_node("report", report)
    graph.add_node("safe_stop", lambda state: {"status": "SAFE_STOPPED"})
    graph.add_node("rejected", lambda state: {"status": "REJECTED"})
    graph.add_edge(START, "requirements")
    graph.add_conditional_edges("requirements", lambda s: "clarification" if s["requirements"]["questions"] else "planning")
    graph.add_edge("clarification", "requirements")
    graph.add_edge("planning", "plan_gate")
    graph.add_conditional_edges("plan_gate", rejected_route,
                                {"approved": "select_task", "rollback_gate": "rollback_gate", "rejected": "rejected"})
    graph.add_conditional_edges("select_task", lambda s: "coding" if s["task_id"] else "consolidate")
    graph.add_edge("coding", "collect")
    graph.add_edge("collect", "select_task")
    graph.add_edge("consolidate", "patch_gate")
    graph.add_conditional_edges("patch_gate", rejected_route,
                                {"approved": "apply", "rollback_gate": "rollback_gate", "rejected": "rejected"})
    graph.add_edge("apply", "testing")
    graph.add_edge("apply", "static_checks")
    graph.add_edge(["testing", "static_checks"], "validation_barrier")
    graph.add_conditional_edges("validation_barrier", validation_route)
    graph.add_edge("review_and_document", "review")
    graph.add_edge("review_and_document", "documentation")
    graph.add_edge(["review", "documentation"], "review_barrier")
    graph.add_conditional_edges("review_barrier", lambda s: "final_gate" if s["review"]["approved"]
                                else ("replan" if s["retry_count"] < runtime.settings.max_retries else "rollback_gate"))
    graph.add_edge("replan", "planning")
    graph.add_conditional_edges("rollback_gate", lambda s: "rollback" if s["approval_granted"] else "safe_stop")
    graph.add_conditional_edges("final_gate", rejected_route,
                                {"approved": "report", "rollback_gate": "rollback_gate", "rejected": "rejected"})
    for terminal in ["report", "rollback", "safe_stop", "rejected"]:
        graph.add_edge(terminal, END)
    return graph.compile(checkpointer=checkpointer)
