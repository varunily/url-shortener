from copy import deepcopy
from pathlib import Path
import json
import sqlite3
import pytest
from pydantic import ValidationError
from langgraph.types import Command
from langgraph.graph.state import CompiledStateGraph
from fastapi.testclient import TestClient
from shortener_orchestrator import cli
from shortener_orchestrator.api import create_app
from shortener_orchestrator.config import Settings
from shortener_orchestrator.governance.paths import PolicyError
from shortener_orchestrator.service import Service
from shortener_orchestrator.tools.repository import worktree_diff
from conftest import decide_and_resume


def request_for(result):
    gate = result["interrupts"][0]
    plan = deepcopy(gate["payload"]["plan"])
    plan["revision"] += 1
    plan["tasks"][0]["description"] += " Preserve all existing click statistics."
    return {"approval_id": gate["approval_id"], "proposal_hash": gate["proposal_hash"],
            "actor": "pytest-simulated-operator", "reason": "Correct missing archival acceptance details",
            "plan": plan}


class NoModelCalls:
    def generate(self, *args, **kwargs):
        raise AssertionError("Plan revision must not invoke an LLM")


def test_revision_revokes_old_authority_and_pauses_before_coding(service, settings):
    original = service.start("brownfield")
    run_id = original["run_id"]
    request = request_for(original)
    directory = Path(original["artifacts"])
    original_plan = (directory / "plans/1.json").read_bytes()
    service.provider_override = NoModelCalls()
    result = service.revise_plan(run_id, request)
    new = result["interrupts"][0]
    assert result["status"] == "AWAITING_APPROVAL"
    assert new["action"] == "plan"
    assert new["proposal_hash"] != request["proposal_hash"]
    assert new["approval_id"] != request["approval_id"]
    assert new["payload"]["plan"] == request["plan"]
    assert new["payload"]["provenance"]["source"] == "operator_supplied_plan"
    assert len(result["pending_approvals"]) == 1
    assert result["retry_count"] == 0
    assert service.store.approval_status(request["approval_id"]) == "superseded"
    assert (directory / "plans/1.json").read_bytes() == original_plan
    assert json.loads((directory / "plans/2.json").read_text()) == request["plan"]
    assert json.loads((directory / "plan.json").read_text()) == request["plan"]
    assert (directory / "plans/2-operator-revision.json").exists()
    assert not worktree_diff(Path(result["workspace"]))
    assert service.runner_factory.calls == 0
    events = service.store.events(run_id)
    assert sum(e["kind"] == "plan_revision_requested" for e in events) == 1
    assert sum(e["kind"] == "plan_revised" for e in events) == 1
    assert not any(e["kind"] == "approval_decided" for e in events)
    assert '"plan_revised"' in (directory / "decisions.jsonl").read_text()
    with pytest.raises(PolicyError, match="stale"):
        service.decide(run_id, request["approval_id"], request["proposal_hash"], "test")
    with pytest.raises(PolicyError, match="pending"):
        service.resume(run_id)
    # Restart retains the new gate; explicit approval proceeds only to patch review.
    restarted = Service(settings, runner_factory=service.runner_factory)
    try:
        assert restarted.inspect(run_id)["interrupts"] == result["interrupts"]
        patched = decide_and_resume(restarted, result)
        assert patched["interrupts"][0]["action"] == "patch"
        assert not worktree_diff(Path(result["workspace"]))
        assert service.runner_factory.calls == 0
    finally:
        restarted.close()


def test_superseded_resume_payload_cannot_advance_new_checkpoint(service):
    original = service.start("brownfield")
    request = request_for(original)
    revised = service.revise_plan(original["run_id"], request)
    state = service.store.get(original["run_id"])["data"]["state"]
    with pytest.raises(PolicyError, match="does not match"):
        service.graph(state).invoke(Command(resume={"approval_id": request["approval_id"],
            "proposal_hash": request["proposal_hash"]}), {"configurable": {"thread_id": original["run_id"]}})
    assert not worktree_diff(Path(revised["workspace"]))
    assert service.runner_factory.calls == 0


@pytest.mark.parametrize("bad", ["hash", "revision", "cycle", "path", "traversal", "actor", "reason", "no_change"])
def test_invalid_revision_preserves_original_gate(service, bad):
    original = service.start("brownfield")
    request = request_for(original)
    if bad == "hash": request["proposal_hash"] = "0" * 64
    if bad == "revision": request["plan"]["revision"] += 1
    if bad == "cycle": request["plan"]["tasks"][0]["depends_on"] = [request["plan"]["tasks"][0]["id"]]
    if bad == "path": request["plan"]["tasks"][0]["files"] = ["pom.xml"]
    if bad == "traversal": request["plan"]["tasks"][0]["files"] = ["src/main/java/com/varun/shortener/../../Escape.java"]
    if bad == "actor": request["actor"] = " "
    if bad == "reason": request["reason"] = " "
    if bad == "no_change": request["plan"] = original["interrupts"][0]["payload"]["plan"] | {"revision": 2}
    before = service.store.events(original["run_id"])
    with pytest.raises((PolicyError, ValidationError)):
        service.revise_plan(original["run_id"], request)
    assert service.inspect(original["run_id"])["interrupts"] == original["interrupts"]
    assert service.store.approval_status(request["approval_id"]) == "pending"
    assert service.store.events(original["run_id"]) == before
    assert service.store.active_plan_revision(original["run_id"]) is None


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_revision_cannot_override_an_operator_decision(service, decision):
    original = service.start("brownfield")
    request = request_for(original)
    service.decide(original["run_id"], request["approval_id"], request["proposal_hash"], "test", decision)
    with pytest.raises(PolicyError, match="decided"):
        service.revise_plan(original["run_id"], request)


def test_revision_rejects_dirty_worktree_and_later_gate_and_honors_lock(service):
    original = service.start("brownfield")
    request = request_for(original)
    run_id = original["run_id"]
    workspace = Path(original["workspace"])
    with service.store.claim(run_id):
        with pytest.raises(PolicyError, match="Another worker"):
            service.revise_plan(run_id, request)
    source = workspace / "README.md"
    previous = source.read_text()
    source.write_text(previous + "\nExternal edit\n")
    with pytest.raises(PolicyError, match="clean worktree"):
        service.revise_plan(run_id, request)
    source.write_text(previous)
    service.stop(run_id)
    with pytest.raises(PolicyError, match="not waiting"):
        service.revise_plan(run_id, request)
    original = service.resume(run_id)
    result = decide_and_resume(service, original)
    assert result["interrupts"][0]["action"] == "patch"
    with pytest.raises(PolicyError, match="Only an undecided plan"):
        service.revise_plan(run_id, request)


@pytest.mark.parametrize("stage", ["journal", "checkpoint", "gate"])
def test_interrupted_revision_recovers_without_approval_or_model_call(service, settings, monkeypatch, stage):
    original = service.start("brownfield")
    request = request_for(original)
    run_id = original["run_id"]
    with monkeypatch.context() as patch:
        if stage == "journal":
            real = service.store.begin_plan_revision
            def fail(*args, **kwargs):
                real(*args, **kwargs)
                raise RuntimeError("simulated process interruption")
            patch.setattr(service.store, "begin_plan_revision", fail)
        elif stage == "checkpoint":
            real = CompiledStateGraph.update_state
            def fail(*args, **kwargs):
                real(*args, **kwargs)
                raise RuntimeError("simulated process interruption")
            patch.setattr(CompiledStateGraph, "update_state", fail)
        else:
            def fail(*args, **kwargs):
                raise RuntimeError("simulated process interruption")
            patch.setattr(service.store, "finish_plan_revision", fail)
        with pytest.raises(RuntimeError, match="interruption"):
            service.revise_plan(run_id, request)
    assert service.store.get(run_id)["status"] == "REVISING_PLAN"
    assert service.store.approval_status(request["approval_id"]) == "superseded"
    for item in service.store.pending(run_id):
        with pytest.raises(PolicyError, match="not waiting"):
            service.decide(run_id, item["id"], item["proposal_hash"], "test")
    service.stop(run_id)
    with pytest.raises(PolicyError, match="stopped"):
        service.revise_plan(run_id, request)
    restarted = Service(settings, provider_override=NoModelCalls(), runner_factory=service.runner_factory)
    try:
        result = restarted.resume(run_id)
        assert result["status"] == "AWAITING_APPROVAL"
        assert result["interrupts"][0]["action"] == "plan"
        assert result["interrupts"][0]["payload"]["plan"] == request["plan"]
        assert len(result["pending_approvals"]) == 1
        assert restarted.store.active_plan_revision(run_id) is None
        assert sum(e["kind"] == "plan_revised" for e in restarted.store.events(run_id)) == 1
        assert not any(e["kind"] == "approval_decided" for e in restarted.store.events(run_id))
        with pytest.raises(PolicyError, match="pending"):
            restarted.resume(run_id)
        assert not worktree_diff(Path(result["workspace"]))
        assert service.runner_factory.calls == 0
    finally:
        restarted.close()


def test_cli_registers_revision_without_approving(service, settings, monkeypatch, capsys):
    original = service.start("brownfield")
    request = request_for(original)
    path = settings.home / "corrected.json"
    path.write_text(json.dumps(request["plan"]))
    monkeypatch.setattr(Settings, "discover", classmethod(lambda cls, repo=None: settings))
    assert cli.main(["revise-plan", original["run_id"], "--plan-file", str(path),
        "--approval-id", request["approval_id"], "--proposal-hash", request["proposal_hash"],
        "--actor", request["actor"], "--reason", request["reason"]]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "AWAITING_APPROVAL"
    assert result["interrupts"][0]["payload"]["plan"] == request["plan"]
    assert not worktree_diff(Path(result["workspace"]))


def test_api_revision_uses_same_gate_and_rejects_old_approval(service, settings):
    original = service.start("brownfield")
    request = request_for(original)
    with TestClient(create_app(settings)) as client:
        url = "/runs/" + original["run_id"]
        response = client.post(url + "/revise-plan", json=request)
        assert response.status_code == 200
        assert response.json()["interrupts"][0]["payload"]["plan"] == request["plan"]
        assert client.post(url + "/resume").status_code == 409
        assert client.post(url + "/decision", json={key: request[key] for key in
            ("approval_id", "proposal_hash", "actor")} | {"decision": "approve"}).status_code == 409


def test_journal_transaction_failure_keeps_original_authority(service):
    original = service.start("brownfield")
    request = request_for(original)
    service.store.db.executescript("""
        CREATE TRIGGER simulate_journal_failure BEFORE INSERT ON events
        WHEN NEW.kind = 'plan_revision_requested'
        BEGIN SELECT RAISE(ABORT, 'simulated journal failure'); END;
    """)
    with pytest.raises(sqlite3.IntegrityError, match="journal failure"):
        service.revise_plan(original["run_id"], request)
    assert service.store.active_plan_revision(original["run_id"]) is None
    assert service.store.approval_status(request["approval_id"]) == "pending"
    assert service.store.get(original["run_id"])["status"] == "AWAITING_APPROVAL"
    assert service.inspect(original["run_id"])["interrupts"] == original["interrupts"]


def test_cli_rejects_plan_file_outside_project(service, settings, monkeypatch, capsys):
    original = service.start("brownfield")
    request = request_for(original)
    monkeypatch.setattr(Settings, "discover", classmethod(lambda cls, repo=None: settings))
    assert cli.main(["revise-plan", original["run_id"], "--plan-file", "/etc/hosts",
        "--approval-id", request["approval_id"], "--proposal-hash", request["proposal_hash"],
        "--actor", request["actor"], "--reason", request["reason"]]) == 1
    assert "inside the project" in capsys.readouterr().err
    assert service.store.approval_status(request["approval_id"]) == "pending"
