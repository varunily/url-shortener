from copy import deepcopy
from pathlib import Path
import json
import pytest
from shortener_orchestrator.service import Service
from shortener_orchestrator.governance.paths import PolicyError
from shortener_orchestrator.tools.repository import worktree_diff
from conftest import decide_and_resume


def request_for(result, settings):
    gate = result["interrupts"][0]
    reader = Service(settings)
    try:
        proposal = deepcopy(reader.store.get(result["run_id"])["data"]["state"]["proposal"])
    finally:
        reader.close()
    proposal["summary"] = "Codex-reviewed correction of the generated patch"
    proposal["changes"][0]["content"] += "\n-- review correction\n"
    return {"approval_id": gate["approval_id"], "proposal_hash": gate["proposal_hash"],
            "actor": "pytest-reviewer", "reason": "Fix reviewed patch defects and preserve exact approved scope",
            "proposal": proposal}


def test_patch_revision_supersedes_pending_authority_and_pauses_again(service, settings):
    first = decide_and_resume(service, service.start("brownfield"))
    assert first["interrupts"][0]["action"] == "patch"
    run_id = first["run_id"]
    old = first["interrupts"][0]
    oldbytes = Path(old["payload"]["patch"]).read_bytes()
    request = request_for(first, settings)
    revised = service.revise_patch(run_id, request)
    new = revised["interrupts"][0]
    assert revised["status"] == "AWAITING_APPROVAL"
    assert new["action"] == "patch"
    assert new["approval_id"] != old["approval_id"]
    assert new["proposal_hash"] != old["proposal_hash"]
    assert revised["pending_approvals"][0]["id"] == new["approval_id"]
    assert service.store.approval_status(old["approval_id"]) == "superseded"
    assert service.store.approval_status(new["approval_id"]) == "pending"
    assert Path(old["payload"]["patch"]).read_bytes() == oldbytes
    assert Path(new["payload"]["patch"]).exists()
    assert not (Path(first["artifacts"]) / "operations.json").exists()
    assert not worktree_diff(Path(first["workspace"]))
    events = service.store.events(run_id)
    assert sum(e["kind"] == "patch_revision_requested" for e in events) == 1
    assert sum(e["kind"] == "patch_revised" for e in events) == 1
    assert not any(e["kind"] == "changes_applied" for e in events)
    with pytest.raises(PolicyError, match="stale"):
        service.decide(run_id, old["approval_id"], old["proposal_hash"], "pytest-reviewer")
    with pytest.raises(PolicyError, match="pending"):
        service.resume(run_id)


@pytest.mark.parametrize("mutation", ["hash", "scope", "missing", "dirty"])
def test_patch_revision_rejects_invalid_requests_without_revoking_old_gate(service, settings, mutation):
    first = decide_and_resume(service, service.start("brownfield"))
    request = request_for(first, settings)
    if mutation == "hash": request["proposal_hash"] = "0" * 64
    if mutation == "scope": request["proposal"]["changes"][0]["path"] = "pom.xml"
    if mutation == "missing": request["proposal"]["changes"].pop()
    if mutation == "dirty": (Path(first["workspace"]) / "README.md").write_text("external change")
    before = service.store.events(first["run_id"])
    with pytest.raises(PolicyError):
        service.revise_patch(first["run_id"], request)
    assert service.store.approval_status(request["approval_id"]) == "pending"
    assert service.store.active_patch_revision(first["run_id"]) is None
    if mutation != "dirty":
        assert service.store.events(first["run_id"]) == before


def test_patch_revision_is_blocked_after_an_operator_decision(service, settings):
    first = decide_and_resume(service, service.start("brownfield"))
    gate = first["interrupts"][0]
    request = request_for(first, settings)
    service.decide(first["run_id"], gate["approval_id"], gate["proposal_hash"], "pytest-reviewer", "reject")
    with pytest.raises(PolicyError, match="stale"):
        service.revise_patch(first["run_id"], request)


def test_patch_revision_rejects_summary_only_noop(service, settings):
    first = decide_and_resume(service, service.start("brownfield"))
    request = request_for(first, settings)
    reader = Service(settings)
    try:
        request["proposal"] = deepcopy(reader.store.get(first["run_id"])["data"]["state"]["proposal"])
    finally:
        reader.close()
    with pytest.raises(PolicyError, match="no file-content changes"):
        service.revise_patch(first["run_id"], request)
    assert service.store.approval_status(request["approval_id"]) == "pending"
    assert service.store.active_patch_revision(first["run_id"]) is None


@pytest.mark.parametrize("stage", ["journal", "checkpoint", "gate"])
def test_patch_revision_recovers_durably_without_applying_code(service, settings, monkeypatch, stage):
    first = decide_and_resume(service, service.start("brownfield"))
    run_id = first["run_id"]
    request = request_for(first, settings)
    with monkeypatch.context() as patch:
        if stage == "journal":
            real = service.store.begin_patch_revision
            def fail(*args, **kwargs):
                real(*args, **kwargs)
                raise RuntimeError("simulated interruption")
            patch.setattr(service.store, "begin_patch_revision", fail)
        elif stage == "checkpoint":
            from langgraph.graph.state import CompiledStateGraph
            real = CompiledStateGraph.update_state
            def fail(*args, **kwargs):
                real(*args, **kwargs)
                raise RuntimeError("simulated interruption")
            patch.setattr(CompiledStateGraph, "update_state", fail)
        else:
            real = service.store.finish_patch_revision
            def fail(*args, **kwargs):
                raise RuntimeError("simulated interruption")
            patch.setattr(service.store, "finish_patch_revision", fail)
        with pytest.raises(RuntimeError, match="interruption"):
            service.revise_patch(run_id, request)
    assert service.store.approval_status(request["approval_id"]) == "superseded"
    restarted = Service(settings, runner_factory=service.runner_factory)
    try:
        result = restarted.resume(run_id)
        assert result["status"] == "AWAITING_APPROVAL"
        assert result["interrupts"][0]["action"] == "patch"
        assert len(result["pending_approvals"]) == 1
        assert restarted.store.active_patch_revision(run_id) is None
        assert not worktree_diff(Path(result["workspace"]))
        assert not (Path(result["artifacts"]) / "operations.json").exists()
    finally:
        restarted.close()
