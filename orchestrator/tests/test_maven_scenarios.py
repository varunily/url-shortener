"""CLI acceptance with synthetic test operators and real Maven/PostgreSQL execution."""
from pathlib import Path
import json
import os
import subprocess
import sys
import pytest
from conftest import clean_worktrees

@pytest.mark.maven
@pytest.mark.parametrize("scenario", ["greenfield", "brownfield", "ambiguous", "retry_rollback"])
def test_real_maven_scenario_from_cli(settings, scenario):
    env = os.environ | {"ORCHESTRATOR_RUNTIME_ROOT": str(settings.home),
                        "PYTHONPATH": str(settings.repo / "orchestrator/src")}
    transcript = settings.home / "cli-transcript.jsonl"
    settings.home.mkdir(parents=True, exist_ok=True)
    def cli(*arguments):
        command = [sys.executable, "-m", "shortener_orchestrator", "--repo", str(settings.repo), *arguments]
        completed = subprocess.run(command, cwd=settings.repo, env=env, capture_output=True, text=True, timeout=360)
        with transcript.open("a") as file:
            file.write(json.dumps({"argv": arguments, "returncode": completed.returncode,
                                   "stdout": completed.stdout, "stderr": completed.stderr}) + "\n")
        assert completed.returncode == 0, completed.stdout + completed.stderr
        return json.loads(completed.stdout)
    try:
        result = cli("run", scenario, "--provider", "fake")
        if scenario == "ambiguous":
            assert result["status"] == "AWAITING_CLARIFICATION"
            result = cli("clarify", result["run_id"], "--answers-json", json.dumps(
                {"url_policy": "http_https", "max_expiration_days": 30, "cleanup": "archive"}),
                "--actor", "pytest-simulated-operator")
        for _ in range(16):
            if result["status"] != "AWAITING_APPROVAL":
                break
            inspected = cli("inspect", result["run_id"])
            pending = inspected["pending_approvals"][0]
            # Test-only simulated operator: production CLI has no auto-approval path.
            cli("approve", result["run_id"], "--approval-id", pending["id"],
                "--proposal-hash", pending["proposal_hash"], "--actor", "pytest-simulated-operator")
            result = cli("resume", result["run_id"])
        directory = Path(result["artifacts"])
        assert (directory / "audit.jsonl").stat().st_size > 0
        metrics = json.loads((directory / "metrics.json").read_text())
        if scenario == "retry_rollback":
            assert result["status"] == "ROLLED_BACK"
            assert metrics["retry_count"] == 3 and metrics["rollback_count"] == 1
            results = [json.loads(path.read_text()) for path in (directory / "tests").glob("*.json")]
            assert len(results) == 4
            assert all(not item["passed"] and item["failures"] >= 1 for item in results)
        else:
            assert result["status"] == "READY", json.dumps(result)
            evidence = json.loads((directory / "tests/1.json").read_text())
            assert evidence["unit_tests"] >= 59
            assert evidence["integration_tests"] > 16
            assert evidence["failures"] == evidence["errors"] == evidence["skipped"] == 0
            assert (directory / "release-readiness.md").exists()
    finally:
        clean_worktrees(settings)
