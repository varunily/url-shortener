from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict
from .models import ApprovalDecision, PlanRevisionRequest
from .service import Service
from .governance.paths import PolicyError

class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str
    provider: str = "fake"

class ClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: dict
    actor: str

def create_app(settings):
    # A fresh SQLite connection per call; per-run OS locks reject competing workers.
    def call(method, *args):
        service = Service(settings)
        try:
            return getattr(service, method)(*args)
        except (PolicyError, ValueError, KeyError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        finally:
            service.close()

    app = FastAPI(title="URL Shortener Orchestrator", version="0.1.0")

    @app.post("/runs")
    def start(body: RunRequest):
        return call("start", body.scenario, body.provider)

    @app.get("/runs/{run_id}")
    def inspect(run_id: str):
        return call("inspect", run_id)

    @app.post("/runs/{run_id}/decision")
    def decide(run_id: str, body: ApprovalDecision):
        return call("decide", run_id, body.approval_id, body.proposal_hash,
                    body.actor, body.decision, body.reason)

    @app.post("/runs/{run_id}/resume")
    def resume(run_id: str):
        return call("resume", run_id)

    @app.post("/runs/{run_id}/revise-plan")
    def revise_plan(run_id: str, body: PlanRevisionRequest):
        return call("revise_plan", run_id, body.model_dump())

    @app.post("/runs/{run_id}/clarify")
    def clarify(run_id: str, body: ClarificationRequest):
        return call("clarify", run_id, body.answers, body.actor)

    @app.post("/runs/{run_id}/stop")
    def stop(run_id: str):
        return call("stop", run_id)

    @app.get("/metrics")
    def metrics():
        service = Service(settings)
        try:
            return service.store.aggregate()
        finally:
            service.close()
    return app
