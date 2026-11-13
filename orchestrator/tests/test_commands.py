from dataclasses import replace
from pathlib import Path
import sys
import time
import pytest
from shortener_orchestrator.tools.commands import CommandRunner, Stopped
from shortener_orchestrator.tools.test_reports import parse_reports

# These executables are controlled test doubles, never used as Maven evidence.
def stub_maven(tmp_path, monkeypatch, body):
    path = tmp_path / "stub-mvn"
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(0o700)
    monkeypatch.setattr("shortener_orchestrator.tools.commands.shutil.which", lambda name: str(path))

def test_timeout_kills_process_and_redacts_captured_log(service, settings, tmp_path, monkeypatch):
    run = service.start("greenfield")
    stub_maven(tmp_path, monkeypatch, "import time\nprint('password=secret-value', flush=True)\ntime.sleep(10)\n")
    runner = CommandRunner(replace(settings, command_timeout=0.2), service.store)
    started = time.monotonic()
    result = runner.run(run["run_id"], Path(run["workspace"]), 1)
    assert time.monotonic() - started < 5
    assert not result.passed and result.classification == "timeout"
    assert "secret-value" not in Path(result.log_path).read_text()

def test_stop_terminates_active_command(service, settings, tmp_path, monkeypatch):
    run = service.start("greenfield")
    stub_maven(tmp_path, monkeypatch, "import time\ntime.sleep(10)\n")
    service.stop(run["run_id"])
    with pytest.raises(Stopped):
        CommandRunner(settings, service.store).run(run["run_id"], Path(run["workspace"]), 1)

def test_exit_zero_without_tests_is_not_success(service, settings, tmp_path, monkeypatch):
    run = service.start("greenfield")
    stub_maven(tmp_path, monkeypatch, "print('No tests ran')\n")
    result = CommandRunner(settings, service.store).run(run["run_id"], Path(run["workspace"]), 1)
    assert result.returncode == 0
    assert not result.passed

def test_execution_environment_strips_application_and_provider_secrets(settings, monkeypatch):
    for key in ["DB_PASSWORD", "OPENAI_API_KEY", "OLLAMA_API_KEY", "MAVEN_OPTS", "JAVA_TOOL_OPTIONS"]:
        monkeypatch.setenv(key, "secret")
    env = CommandRunner(settings, None).environment()
    assert not set(env).intersection({"DB_PASSWORD", "OPENAI_API_KEY", "OLLAMA_API_KEY", "MAVEN_OPTS", "JAVA_TOOL_OPTIONS"})

def test_report_parser_keeps_failures_errors_and_skips(tmp_path):
    report = tmp_path / "target/failsafe-reports/TEST-example.xml"
    report.parent.mkdir(parents=True)
    report.write_text('<testsuite tests="4" failures="1" errors="1" skipped="1"/>')
    assert parse_reports(tmp_path) == {"unit_tests": 0, "integration_tests": 4, "failures": 1, "errors": 1, "skipped": 1}
