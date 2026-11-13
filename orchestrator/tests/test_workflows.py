from pathlib import Path
import json
import threading
import time
import pytest
from langgraph.types import Command
from shortener_orchestrator.service import Service
from shortener_orchestrator.governance.paths import PolicyError
from shortener_orchestrator.llm.fake import FakeLLM
from shortener_orchestrator.tools.repository import git, worktree_diff
from conftest import decide_and_resume, finish_test_workflow, FakeRunner, clean_worktrees

def test_plan_and_patch_gates_prevent_unapproved_writes(service):
    result = service.start("greenfield")
    workspace = Path(result["workspace"])
    assert result["status"] == "AWAITING_APPROVAL"
    assert result["interrupts"][0]["action"] == "plan"
    assert not worktree_diff(workspace)
    with pytest.raises(PolicyError, match="pending"):
        service.resume(result["run_id"])
    result = decide_and_resume(service, result)
    assert result["interrupts"][0]["action"] == "patch"
    assert not worktree_diff(workspace)
    patch = Path(result["interrupts"][0]["payload"]["patch"])
    assert "customAlias" in patch.read_text()
    result = decide_and_resume(service, result)
    assert result["interrupts"][0]["action"] == "release"
    assert "customAlias" in worktree_diff(workspace)
    result = decide_and_resume(service, result)
    assert result["status"] == "READY"
    assert (Path(result["artifacts"]) / "release-readiness.md").exists()

def test_forged_resume_cannot_approve(service):
    result = service.start("brownfield")
    run_id = result["run_id"]
    state = service.store.get(run_id)["data"]["state"]
    item = result["interrupts"][0]
    with pytest.raises(PolicyError, match="persisted"):
        service.graph(state).invoke(Command(resume={"approval_id": item["approval_id"],
                                                   "proposal_hash": item["proposal_hash"]}),
                                    {"configurable": {"thread_id": run_id}})
    assert not worktree_diff(Path(result["workspace"]))

def test_wrong_hash_and_replayed_decisions_are_rejected(service):
    result = service.start("brownfield")
    item = result["pending_approvals"][0]
    with pytest.raises(PolicyError):
        service.decide(result["run_id"], item["id"], "wrong", "test", "approve")
    service.decide(result["run_id"], item["id"], item["proposal_hash"], "test", "approve")
    with pytest.raises(PolicyError):
        service.decide(result["run_id"], item["id"], item["proposal_hash"], "test", "approve")

def test_rejecting_initial_plan_is_terminal_and_writes_nothing(service):
    result = service.start("brownfield")
    result = decide_and_resume(service, result, "reject")
    assert result["status"] == "REJECTED"
    assert not worktree_diff(Path(result["workspace"]))

def test_ambiguous_requirement_pauses_then_uses_human_answers(service):
    result = service.start("ambiguous")
    assert result["status"] == "AWAITING_CLARIFICATION"
    assert result["interrupts"][0]["questions"]
    result = service.clarify(result["run_id"],
                            {"url_policy": "http_https", "max_expiration_days": 7, "cleanup": "archive"},
                            "pytest-simulated-human")
    assert result["status"] == "AWAITING_APPROVAL"
    result = finish_test_workflow(service, result)
    assert result["status"] == "READY"
    assert "Duration.ofDays(7)" in (Path(result["workspace"]) /
        "src/main/java/com/varun/shortener/service/UrlService.java").read_text()
    assert any(e["kind"] == "clarified" for e in service.store.events(result["run_id"]))

def test_restart_preserves_checkpoint_and_decision(service, settings):
    result = service.start("brownfield")
    run_id = result["run_id"]
    pending = result["pending_approvals"][0]
    service.decide(run_id, pending["id"], pending["proposal_hash"], "test")
    restarted = Service(settings, runner_factory=service.runner_factory)
    try:
        result = restarted.resume(run_id)
        assert result["interrupts"][0]["action"] == "patch"
        assert not worktree_diff(Path(result["workspace"]))
        result = finish_test_workflow(restarted, result)
        assert result["status"] == "READY"
    finally:
        restarted.close()

def test_three_retries_then_explicit_rollback_gate(service):
    service.runner_factory.failures = 100
    result = service.start("retry_rollback")
    while result["status"] == "AWAITING_APPROVAL" and result["interrupts"][0]["action"] != "rollback":
        result = decide_and_resume(service, result)
    assert result["retry_count"] == 3
    assert service.runner_factory.calls == 4
    assert result["interrupts"][0]["action"] == "rollback"
    assert worktree_diff(Path(result["workspace"]))
    result = decide_and_resume(service, result)
    assert result["status"] == "ROLLED_BACK"
    assert not worktree_diff(Path(result["workspace"]))
    metrics = json.loads((Path(result["artifacts"]) / "metrics.json").read_text())
    assert metrics["retry_count"] == 3
    assert metrics["rollback_count"] == 1
    assert metrics["agent_outcomes"]["testing"]["failure"] == 4
    assert metrics["mean_time_to_recovery_seconds"] is not None

def test_one_failed_validation_replans_and_recovers(service):
    service.runner_factory.failures = 1
    result = finish_test_workflow(service, service.start("brownfield", fault="once"))
    assert result["status"] == "READY"
    assert result["retry_count"] == 1
    assert service.runner_factory.calls == 2
    metrics = json.loads((Path(result["artifacts"]) / "metrics.json").read_text())
    assert metrics["mean_time_to_recovery_seconds"] is not None

def test_parallel_validation_and_review_barriers(service):
    static_started = threading.Event()
    original_event = service.store.event
    def event(run_id, kind, data, key=None):
        if kind == "static_started":
            static_started.set()
        original_event(run_id, kind, data, key)
    service.store.event = event
    class WaitingRunner(FakeRunner):
        def run(self, *args, **kwargs):
            assert static_started.wait(5), "Static checks did not run in parallel with tests"
            return super().run(*args, **kwargs)
    barrier = threading.Barrier(2)
    class ParallelProvider(FakeLLM):
        def generate(self, agent, schema, context):
            if agent in {"review", "documentation"}:
                barrier.wait(timeout=5)
            return super().generate(agent, schema, context)
    service.runner_factory = WaitingRunner
    service.provider_override = ParallelProvider()
    result = finish_test_workflow(service, service.start("greenfield"))
    assert result["status"] == "READY"
    events = service.store.events(result["run_id"])
    order = {e["kind"]: e["seq"] for e in events}
    assert order["static_finished"] < order["validation_barrier"]

def test_safe_stop_prevents_writes_and_can_resume(service):
    result = service.start("greenfield")
    result = decide_and_resume(service, result)
    item = result["pending_approvals"][0]
    service.decide(result["run_id"], item["id"], item["proposal_hash"], "test")
    service.stop(result["run_id"])
    # Direct invocation sees the durable stop flag before applying the approved patch.
    state = service.store.get(result["run_id"])["data"]["state"]
    stopped = service._drive(state, Command(resume={"approval_id": item["id"], "proposal_hash": item["proposal_hash"]}))
    assert stopped["status"] == "STOPPED"
    assert not worktree_diff(Path(result["workspace"]))
    resumed = service.resume(result["run_id"])
    assert resumed["interrupts"][0]["action"] == "release"

def test_concurrent_workers_cannot_claim_the_same_run(service):
    result = service.start("brownfield")
    with service.store.claim(result["run_id"]):
        with pytest.raises(PolicyError, match="Another worker"):
            with service.store.claim(result["run_id"]):
                pass

def test_worktree_path_with_spaces_and_shared_git_history(service, settings):
    result = service.start("brownfield")
    assert " " in str(settings.repo)
    workspace = Path(result["workspace"])
    assert git(workspace, "rev-parse", "HEAD").strip() == git(settings.repo, "rev-parse", "HEAD").strip()
    assert not worktree_diff(workspace)

def test_stopping_waiting_run_preserves_gate_and_requires_resume(service):
    result = service.start("greenfield")
    run_id = result["run_id"]
    stopped = service.stop(run_id)
    assert stopped["status"] == "STOPPED"
    item = stopped["pending_approvals"][0]
    with pytest.raises(PolicyError, match="not waiting"):
        service.decide(run_id, item["id"], item["proposal_hash"], "test")
    resumed = service.resume(run_id)
    assert resumed["status"] == "AWAITING_APPROVAL"
    assert not worktree_diff(Path(result["workspace"]))
    assert not service.store.stopped(run_id)

def test_resume_and_clarify_hold_run_lock_before_reading_checkpoint(service):
    result = service.start("ambiguous")
    with service.store.claim(result["run_id"]):
        with pytest.raises(PolicyError, match="Another worker"):
            service.resume(result["run_id"])
        with pytest.raises(PolicyError, match="Another worker"):
            service.clarify(result["run_id"], {}, "test")

def test_rejected_rollback_cannot_be_bypassed_with_resume(service):
    service.runner_factory.failures = 100
    result = service.start("retry_rollback")
    while result["interrupts"][0]["action"] != "rollback":
        result = decide_and_resume(service, result)
    result = decide_and_resume(service, result, "reject")
    assert result["status"] == "SAFE_STOPPED"
    with pytest.raises(PolicyError, match="Rollback was rejected"):
        service.resume(result["run_id"])
    assert service.runner_factory.calls == 4

def test_environment_safe_stop_resumes_validation_without_recoding(service):
    class EnvironmentRunner(FakeRunner):
        calls = 0
        failures = 1
        def run(self, *args, **kwargs):
            result = super().run(*args, **kwargs)
            if not result.passed:
                result.classification = "environment"
            return result
    service.runner_factory = EnvironmentRunner
    result = service.start("brownfield")
    result = decide_and_resume(service, decide_and_resume(service, result))
    assert result["status"] == "SAFE_STOPPED"
    assert result["retry_count"] == 0
    result = service.resume(result["run_id"])
    assert result["interrupts"][0]["action"] == "release"
    assert result["retry_count"] == 0

def test_ollama_preflight_failure_is_explicit_without_fake_fallback(service, monkeypatch):
    from shortener_orchestrator.llm.ollama import OllamaProvider
    def unavailable(self):
        raise RuntimeError("Ollama not available")
    monkeypatch.setattr(OllamaProvider, "available", unavailable)
    result = service.start("greenfield", provider="ollama")
    assert result["status"] == "FAILED"
    assert result["provider"] == "ollama"
    assert not Path(result["workspace"]).exists()
    events = service.store.events(result["run_id"])
    assert any(e["kind"] == "preflight_failed" for e in events)
    assert not any(e["kind"] == "agent_started" for e in events)

def test_rejected_model_plan_is_preserved_and_counted_as_failure(service):
    from shortener_orchestrator.models import Plan
    class InvalidPlanner(FakeLLM):
        def generate(self, agent, schema, context):
            if agent == "planning":
                return Plan(revision=1, tasks=[{"id": "bad", "description": "protected change",
                    "depends_on": [], "files": ["pom.xml"]}])
            return super().generate(agent, schema, context)
    service.provider_override = InvalidPlanner()
    result = service.start("brownfield")
    assert result["status"] == "SAFE_STOPPED"
    events = service.store.events(result["run_id"])
    assert any(e["kind"] == "agent_failed" and e["data"]["agent"] == "planning" for e in events)
    assert not any(e["kind"] == "agent_succeeded" and e["data"]["agent"] == "planning" for e in events)
    proposals = list((Path(result["artifacts"]) / "plans").glob("*-proposal-*.json"))
    assert len(proposals) == 1
    assert "pom.xml" in proposals[0].read_text()
    assert not worktree_diff(Path(result["workspace"]))

def test_resumed_planner_receives_previous_policy_failure(service):
    from shortener_orchestrator.models import Plan
    class CorrectingPlanner(FakeLLM):
        def generate(self, agent, schema, context):
            if agent == "planning":
                if not context.get("previous_execution_error"):
                    return Plan(revision=1, tasks=[{"id": "bad", "description": "protected change",
                        "depends_on": [], "files": ["pom.xml"]}])
                assert "pom.xml" in context["previous_execution_error"]["detail"]
            return super().generate(agent, schema, context)
    service.provider_override = CorrectingPlanner()
    result = service.start("brownfield")
    assert result["status"] == "SAFE_STOPPED"
    result = service.resume(result["run_id"])
    assert result["status"] == "AWAITING_APPROVAL"
    assert result["interrupts"][0]["action"] == "plan"

@pytest.mark.parametrize("failure", ["scope", "hash", "missing"])
def test_coding_rejects_bad_proposals_before_collection_and_preserves_evidence(service, failure):
    from shortener_orchestrator.models import ChangeSet
    class InvalidCoder(FakeLLM):
        def generate(self, agent, schema, context):
            value = super().generate(agent, schema, context)
            if agent == "coding":
                data = value.model_dump()
                if failure == "scope": data["changes"][0]["path"] = "src/test/java/com/varun/shortener/UnexpectedTest.java"
                if failure == "hash": data["changes"][0]["before_sha256"] = "wrong"
                if failure == "missing": data["changes"] = data["changes"][:1]
                return ChangeSet.model_validate(data)
            return value
    service.provider_override = InvalidCoder()
    result = decide_and_resume(service, service.start("brownfield"))
    assert result["status"] == "SAFE_STOPPED"
    events = service.store.events(result["run_id"])
    assert any(e["kind"] == "agent_failed" and e["data"]["agent"] == "coding" for e in events)
    assert not any(e["kind"] == "agent_succeeded" and e["data"]["agent"] == "coding" for e in events)
    assert list((Path(result["artifacts"]) / "proposals").glob("*-attempt-*.json"))
    assert not worktree_diff(Path(result["workspace"]))

def test_review_feedback_requeues_unapplied_dependants_without_reapproving_plan(service):
    class PausingCoder(FakeLLM):
        def generate(self, agent, schema, context):
            if agent == "coding" and context["task"]["id"] == "implementation":
                raise RuntimeError("simulated review pause")
            return super().generate(agent, schema, context)
    service.provider_override = PausingCoder()
    result = decide_and_resume(service, service.start("brownfield"))
    run_id = result["run_id"]
    assert result["status"] == "SAFE_STOPPED"
    assert service.store.get(run_id)["data"]["state"]["completed_tasks"] == ["schema"]
    result = service.rework_coding(run_id, "schema", "Use ALTER TABLE for the existing table", "pytest-reviewer")
    assert result["status"] == "STOPPED"
    state = service.store.get(run_id)["data"]["state"]
    assert not state["completed_tasks"] and not state["pending_changes"]
    assert state["plan"]["revision"] == 1
    class CorrectedCoder(FakeLLM):
        def generate(self, agent, schema, context):
            if agent == "coding" and context["task"]["id"] == "schema":
                assert "ALTER TABLE" in context["coding_feedback"]
            return super().generate(agent, schema, context)
    service.provider_override = CorrectedCoder()
    result = service.resume(run_id)
    assert result["interrupts"][0]["action"] == "patch"
    assert not worktree_diff(Path(result["workspace"]))
    assert service.runner_factory.calls == 0
    events = service.store.events(run_id)
    assert sum(e["kind"] == "approval_decided" for e in events) == 1
    assert any(e["kind"] == "coding_rework_requested" for e in events)
    service.stop(run_id)
    with pytest.raises(PolicyError, match="pending gate"):
        service.rework_coding(run_id, "schema", "Do more", "test")

def test_coding_generation_has_at_most_three_retries(service):
    class FailingCoder(FakeLLM):
        calls = 0
        def generate(self, agent, schema, context):
            if agent == "coding":
                self.calls += 1
                raise RuntimeError("persistent coding failure")
            return super().generate(agent, schema, context)
    provider = FailingCoder()
    service.provider_override = provider
    result = decide_and_resume(service, service.start("brownfield"))
    for _ in range(4):
        result = service.resume(result["run_id"])
    assert provider.calls == 4
    assert result["status"] == "SAFE_STOPPED"
    with pytest.raises(PolicyError, match="three retries"):
        service.rework_coding(result["run_id"], "schema", "Retry again", "test")
    assert not worktree_diff(Path(result["workspace"]))
