import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from shortener_orchestrator import cli
from shortener_orchestrator.api import create_app
from shortener_orchestrator.config import Settings

def test_cli_inspects_persistent_run(service, settings, monkeypatch, capsys):
    result = service.start("brownfield")
    monkeypatch.setattr(Settings, "discover", classmethod(lambda cls, repo=None: settings))
    assert cli.main(["inspect", result["run_id"]]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "AWAITING_APPROVAL"

def test_cli_does_not_have_an_auto_approve_option():
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["run", "greenfield", "--auto-approve"])

def test_minimal_api_uses_same_checkpoint_and_blocks_unapproved_resume(service, settings):
    result = service.start("brownfield")
    with TestClient(create_app(settings)) as client:
        response = client.get("/runs/" + result["run_id"])
        assert response.status_code == 200
        assert response.json()["status"] == "AWAITING_APPROVAL"
        response = client.post("/runs/" + result["run_id"] + "/resume")
        assert response.status_code == 409
        assert client.get("/metrics").json()["pending_or_stopped"] == 1

def test_cli_model_override_is_passed_to_new_run(settings, monkeypatch, capsys):
    observed = {}
    monkeypatch.setattr(Settings, "discover", classmethod(lambda cls, repo=None: settings))
    class CapturingService:
        def __init__(self, selected):
            observed["model"] = selected.model
        def start(self, scenario, provider, fault):
            observed.update(scenario=scenario, provider=provider)
            return {"status": "AWAITING_APPROVAL", "model": observed["model"]}
        def close(self):
            pass
    monkeypatch.setattr(cli, "Service", CapturingService)
    assert cli.main(["run", "brownfield", "--provider", "ollama", "--model", "selected-model:7b"]) == 0
    assert observed == {"model": "selected-model:7b", "scenario": "brownfield", "provider": "ollama"}
    assert json.loads(capsys.readouterr().out)["model"] == "selected-model:7b"

def test_fake_run_cannot_misrepresent_a_selected_real_model(settings, monkeypatch, capsys):
    monkeypatch.setattr(Settings, "discover", classmethod(lambda cls, repo=None: settings))
    assert cli.main(["run", "brownfield", "--provider", "fake", "--model", "qwen2.5-coder:7b"]) == 1
    assert "only to the Ollama" in capsys.readouterr().err
