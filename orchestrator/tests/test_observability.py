from pathlib import Path
import json
import pytest
from conftest import finish_test_workflow

def test_audit_metrics_and_artifacts_exist_while_waiting(service):
    result = service.start("brownfield")
    root = Path(result["artifacts"])
    for name in ["manifest.json", "audit.jsonl", "metrics.json", "plan.json", "requirements.json", "approvals.jsonl"]:
        assert (root / name).exists()
    assert service.store.aggregate()["success_rate"] is None

def test_audit_redacts_secrets_and_deduplicates_replay(service):
    result = service.start("brownfield")
    run_id = result["run_id"]
    for _ in range(2):
        service.store.event(run_id, "sensitive", {"message": "token=private", "password": "hidden"}, key="once")
    matches = [e for e in service.store.events(run_id) if e["kind"] == "sensitive"]
    assert len(matches) == 1
    assert "private" not in json.dumps(matches)
    assert "hidden" not in json.dumps(matches)

def test_success_rate_excludes_pending_runs(service):
    finished = finish_test_workflow(service, service.start("greenfield"))
    pending = service.start("brownfield")
    metrics = service.store.aggregate()
    assert metrics["successful"] == 1
    assert metrics["pending_or_stopped"] == 1
    assert metrics["success_rate"] == 1.0

def test_repeated_agent_invocations_after_clarification_are_counted_separately(service):
    result = service.start("ambiguous")
    service.clarify(result["run_id"],
        {"url_policy": "http_https", "max_expiration_days": 30, "cleanup": "archive"}, "test-operator")
    events = service.store.events(result["run_id"])
    completed = [e for e in events if e["kind"] == "agent_succeeded" and e["data"]["agent"] == "requirement"]
    assert len(completed) == 2
    assert len({e["data"]["invocation_id"] for e in completed}) == 2
    metrics = json.loads((Path(result["artifacts"]) / "metrics.json").read_text())
    assert metrics["agent_outcomes"]["requirement"]["success"] == 2
