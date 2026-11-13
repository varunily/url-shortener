from pathlib import Path
import json
import os
import time
import pytest
from shortener_orchestrator.config import Settings
from shortener_orchestrator.service import Service
from shortener_orchestrator.models import TestResult
from shortener_orchestrator.tools.repository import git

REPO = Path(__file__).resolve().parents[2]

class FakeRunner:
    """Unit-test execution adapter; these results are never demonstration evidence."""
    calls = 0
    failures = 0
    def __init__(self, settings, store):
        self.settings, self.store = settings, store

    def run(self, run_id, workspace, attempt, profile="verify"):
        type(self).calls += 1
        passed = type(self).calls > type(self).failures
        log = self.store.directory(run_id) / "tests" / f"{attempt}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("UNIT TEST DOUBLE: no Maven executed.\n")
        return TestResult(passed=passed, returncode=0 if passed else 1, unit_tests=1,
                          integration_tests=1, failures=0 if passed else 1,
                          classification="passed" if passed else "validation",
                          log_path=str(log), duration_seconds=0.01)

@pytest.fixture
def settings(tmp_path):
    # --basetemp is explicitly inside this project. Never create a second Git repository.
    return Settings(repo=REPO, runtime_root=tmp_path / "runtime",
                    java_home=os.environ.get("JAVA_HOME", ""), command_timeout=300)

@pytest.fixture
def service(settings):
    class Runner(FakeRunner):
        calls = 0
        failures = 0
    instance = Service(settings, runner_factory=Runner)
    yield instance
    instance.close()
    clean_worktrees(settings)

def clean_worktrees(settings):
    directory = settings.home / "worktrees"
    if directory.exists():
        for workspace in directory.iterdir():
            # Only ephemeral pytest-owned worktrees, never human demonstration runs.
            assert workspace.resolve().is_relative_to(REPO / "orchestrator" / ".tmp")
            git(REPO, "worktree", "remove", "--force", str(workspace))

def decide_and_resume(service, result, decision="approve"):
    pending = result["pending_approvals"]
    assert len(pending) == 1, result
    item = pending[0]
    service.decide(result["run_id"], item["id"], item["proposal_hash"], "pytest-simulated-operator", decision)
    return service.resume(result["run_id"])

def finish_test_workflow(service, result):
    # TEST ONLY: simulate separate human decisions. Production CLI has no auto-approval switch.
    for _ in range(20):
        if result["status"] != "AWAITING_APPROVAL":
            return result
        result = decide_and_resume(service, result)
    raise AssertionError("Workflow did not terminate within test bound")
