from pathlib import Path
from dataclasses import replace
import json
import sqlite3
import uuid
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from .agents.common import AgentContext
from .config import Settings
from .governance.paths import PolicyError
from .governance.redaction import redact
from .llm.fake import FakeLLM
from .llm.ollama import OllamaProvider
from .models import ApprovalDecision, ChangeSet, digest
from .persistence.database import Store
from .tools.commands import CommandRunner, Stopped
from .tools.repository import baseline, git
from .tools.worktrees import Worktrees
from .workflow.graph import build_graph
from .workflow import revisions, gates, patch_revisions

REQUESTS = {
    "greenfield": "Add optional custom aliases: 3–32 case-sensitive Base62 characters, reserved routes rejected, conflicts return 409. Preserve generated seven-character codes.",
    "brownfield": "Preserve 410 Gone / URL_EXPIRED. Add scheduled archival of expired links while preserving mappings and click statistics. Add regressions; full Maven verify must pass.",
    "ambiguous": "Improve URL security and expiration.",
    "retry_rollback": "Add expiration archival and demonstrate an explicit persistent test failure, at most three retries, then approved rollback.",
}

class Service:
    def __init__(self, settings: Settings, provider_override=None, runner_factory=None):
        self.settings = settings
        self.store = Store(settings.home)
        self.worktrees = Worktrees(settings)
        self.provider_override = provider_override
        self.runner_factory = runner_factory or CommandRunner
        self.checkpoint_db = sqlite3.connect(settings.home / ".state/checkpoints.sqlite", check_same_thread=False, timeout=30)
        self.checkpoint_db.execute("PRAGMA journal_mode=WAL")
        self.checkpointer = SqliteSaver(self.checkpoint_db)

    def close(self):
        self.checkpoint_db.close()
        self.store.db.close()

    def graph(self, state):
        provider = self.provider_override or (FakeLLM() if state["provider"] == "fake"
                    else OllamaProvider(replace(self.settings, model=state["model"])))
        runtime = AgentContext(self.settings, self.store, provider, self.runner_factory(self.settings, self.store))
        return build_graph(runtime, self.checkpointer)

    def start(self, scenario, provider="fake", fault=None):
        if scenario not in REQUESTS or provider not in {"fake", "ollama"}:
            raise PolicyError("Unknown scenario or provider")
        if fault not in {None, "once", "always"} or fault and provider != "fake":
            raise PolicyError("Failure injection is available only in explicit FakeLLM demonstrations")
        if scenario == "retry_rollback":
            fault = "always"
        run_id = uuid.uuid4().hex[:12]
        revision = baseline(self.settings.repo)
        workspace = self.settings.home / "worktrees" / run_id
        state = {
            "run_id": run_id, "scenario": scenario, "request": REQUESTS[scenario], "provider": provider,
            "model": "deterministic-fixtures" if provider == "fake" else self.settings.model,
            "baseline": revision, "workspace": str(workspace), "status": "CREATED",
            "revision": 1, "retry_count": 0, "completed_tasks": [], "pending_changes": [],
            "clarification": {}, "fault": fault, "recovery_started": None, "task_id": "",
        }
        self.store.create(run_id, state)
        try:
            if provider == "ollama" and self.provider_override is None:
                OllamaProvider(self.settings).available()
            self.worktrees.create(run_id, revision)
        except Exception as error:
            self.store.event(run_id, "preflight_failed", {"error": redact(str(error)), "type": type(error).__name__})
            self.store.update(run_id, "FAILED", state, terminal=True)
            return self.inspect(run_id)
        return self._drive(state, state)

    def _drive(self, state, input_value):
        run_id = state["run_id"]
        with self.store.claim(run_id):
            return self._drive_claimed(state, input_value)

    def _drive_claimed(self, state, input_value):
        run_id = state["run_id"]
        self.worktrees.validate(Path(state["workspace"]), state["baseline"])
        graph = self.graph(state)
        config = {"configurable": {"thread_id": run_id}, "recursion_limit": 200}
        self.store.update(run_id, "RUNNING", state)
        try:
            graph.invoke(input_value, config)
            snapshot = graph.get_state(config)
            values = dict(snapshot.values)
            interruptions = [item.value for task in snapshot.tasks for item in task.interrupts]
            if interruptions:
                status = "AWAITING_CLARIFICATION" if interruptions[0]["kind"] == "clarification" else "AWAITING_APPROVAL"
                self.store.update(run_id, status, values)
            else:
                status = values.get("status", "FAILED")
                self.store.update(run_id, status, values, terminal=status in {"READY", "REJECTED", "ROLLED_BACK", "FAILED"})
        except Stopped as error:
            snapshot = graph.get_state(config)
            self.store.event(run_id, "stopped", {"reason": str(error)})
            self.store.update(run_id, "STOPPED", dict(snapshot.values))
        except Exception as error:
            snapshot = graph.get_state(config)
            self.store.event(run_id, "execution_error", {"type": type(error).__name__, "detail": redact(str(error))})
            self.store.update(run_id, "SAFE_STOPPED", dict(snapshot.values) or state)
        return self.inspect(run_id)

    def inspect(self, run_id):
        run = self.store.get(run_id)
        state = run["data"].get("state", run["data"])
        graph = self.graph(state)
        snapshot = graph.get_state({"configurable": {"thread_id": run_id}})
        interruptions = [item.value for task in snapshot.tasks for item in task.interrupts]
        return {
            "run_id": run_id, "status": run["status"], "scenario": state["scenario"],
            "provider": state["provider"], "model": state["model"],
            "workspace": state["workspace"], "artifacts": str(self.store.directory(run_id)),
            "retry_count": state.get("retry_count", 0), "interrupts": interruptions,
            "pending_approvals": self.store.pending(run_id),
        }

    def decide(self, run_id, approval_id, proposal_hash, actor, decision="approve", reason=""):
        with self.store.claim(run_id):
            self.store.decide(run_id, ApprovalDecision(approval_id=approval_id, proposal_hash=proposal_hash,
                              actor=actor, decision=decision, reason=reason))
        return self.inspect(run_id)

    def revise_plan(self, run_id, request):
        return revisions.revise(self, run_id, request)

    def revise_patch(self, run_id, request):
        return patch_revisions.revise(self, run_id, request)

    def rework_coding(self, run_id, task_id, feedback, actor):
        """Requeue an unapplied proposal and its dependants under the same approved plan."""
        if not isinstance(feedback, str) or not feedback.strip() or len(feedback) > 12000:
            raise PolicyError("Coding feedback must contain 1–12000 characters")
        if not isinstance(actor, str) or not actor.strip() or len(actor) > 100:
            raise PolicyError("Coding feedback requires an actor")
        with self.store.claim(run_id):
            run = self.store.get(run_id)
            if run["status"] not in {"STOPPED", "SAFE_STOPPED"} or self.store.active_plan_revision(run_id):
                raise PolicyError("Rework requires a stopped coding run")
            state = run["data"]["state"]
            graph = self.graph(state)
            config = {"configurable": {"thread_id": run_id}}
            snapshot = graph.get_state(config)
            state = dict(snapshot.values)
            if revisions.interrupts(snapshot) or self.store.pending(run_id) or state.get("applied_digest"):
                raise PolicyError("Rework cannot bypass a pending gate or modify applied changes")
            approval_id = f"{run_id}:plan:{digest(gates.plan_payload(state))[:16]}"
            if self.store.approval_status(approval_id) != "approve":
                raise PolicyError("Rework requires this exact plan to be approved")
            tasks = {task["id"]: task for task in state["plan"]["tasks"]}
            if task_id not in tasks:
                raise PolicyError("Unknown task in approved plan")
            attempts = sum(event["kind"] == "agent_started" and event["data"].get("agent") == "coding"
                           and event["data"].get("task_id") == task_id
                           and event["data"].get("revision") == state["revision"]
                           for event in self.store.events(run_id))
            if attempts >= 4:
                raise PolicyError("Coding task exhausted its initial attempt plus three retries")
            revisions.check_workspace(self, state)
            invalid = {task_id}
            while True:
                dependants = {key for key, task in tasks.items() if set(task["depends_on"]) & invalid}
                if dependants <= invalid:
                    break
                invalid |= dependants
            completed = [key for key in state.get("completed_tasks", []) if key not in invalid]
            # Reconstruct retained files from individual immutable attempt-derived proposals.
            changes = {}
            for key in completed:
                proposal = json.loads((self.store.directory(run_id) / "proposals" /
                                       f"{state['revision']}-{key}.json").read_text())
                for change in proposal["changes"]:
                    changes[change["path"]] = change
            event = {"task_id": task_id, "revision": state["revision"], "actor": actor, "feedback": feedback,
                     "invalidated_tasks": sorted(invalid), "approved_plan_id": approval_id}
            self.store.event(run_id, "coding_rework_requested", event)
            graph.update_state(config, {"completed_tasks": completed, "pending_changes": list(changes.values()),
                "proposal": {}, "task_proposal": {}, "task_id": "", "approval_granted": True,
                "coding_feedback": state.get("coding_feedback", {}) | {task_id: feedback}}, as_node="plan_gate")
            self.store.update(run_id, "STOPPED", dict(graph.get_state(config).values))
            return self.inspect(run_id)

    def resume(self, run_id):
        with self.store.claim(run_id):
            return self._resume_claimed(run_id)

    def _resume_claimed(self, run_id):
        if self.store.active_patch_revision(run_id):
            self.store.clear_stop(run_id)
            return patch_revisions.complete(self, run_id)
        if self.store.active_plan_revision(run_id):
            self.store.clear_stop(run_id)
            return revisions.complete(self, run_id)
        run = self.store.get(run_id)
        if run["status"] in {"READY", "REJECTED", "ROLLED_BACK", "FAILED"}:
            raise PolicyError("This run is terminal")
        state = run["data"].get("state", run["data"])
        graph = self.graph(state)
        config = {"configurable": {"thread_id": run_id}}
        snapshot = graph.get_state(config)
        interruptions = [item.value for task in snapshot.tasks for item in task.interrupts]
        if interruptions:
            pending = interruptions[0]
            if run["status"] == "STOPPED":
                self.store.clear_stop(run_id)
                status = "AWAITING_CLARIFICATION" if pending["kind"] == "clarification" else "AWAITING_APPROVAL"
                self.store.update(run_id, status, state)
                self.store.event(run_id, "resumed", {"waiting_at_gate": True})
                if pending["kind"] == "clarification" or self.store.approval_status(pending["approval_id"]) == "pending":
                    return self.inspect(run_id)
            if pending["kind"] == "clarification":
                raise PolicyError("Use clarify with explicit answers")
            if self.store.approval_status(pending["approval_id"]) not in {"approve", "reject"}:
                raise PolicyError("Approval is still pending")
            value = Command(resume={"approval_id": pending["approval_id"], "proposal_hash": pending["proposal_hash"]})
        elif not snapshot.next:
            if run["status"] != "SAFE_STOPPED" or not state.get("applied_digest"):
                raise PolicyError("No resumable execution checkpoint")
            if state.get("approval_granted") is False:
                raise PolicyError("Rollback was rejected; the stopped run cannot bypass that decision")
            if state.get("test_result", {}).get("classification") not in {"environment", "timeout"}:
                raise PolicyError("This safe stop requires inspection and a new run")
            # Environment-related safe stops can rerun validation on the same approved source.
            graph.update_state(config, {"status": "VALIDATING"}, as_node="apply")
            value = None
        else:
            value = None
        self.store.clear_stop(run_id)
        self.store.event(run_id, "resumed", {})
        return self._drive_claimed(state, value)

    def clarify(self, run_id, answers, actor):
        with self.store.claim(run_id):
            run = self.store.get(run_id)
            if run["status"] != "AWAITING_CLARIFICATION":
                raise PolicyError("Run is not awaiting clarification")
            if not isinstance(answers, dict) or not isinstance(actor, str) or not actor.strip():
                raise PolicyError("Clarification requires an answer object and operator identity")
            state = run["data"]["state"]
            return self._drive_claimed(state, Command(resume={"answers": answers, "actor": actor}))

    def stop(self, run_id):
        self.store.request_stop(run_id)
        return self.inspect(run_id)
