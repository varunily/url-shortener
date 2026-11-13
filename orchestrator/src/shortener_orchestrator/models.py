from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
import hashlib
import json

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Requirements(StrictModel):
    summary: str
    acceptance: list[str] = Field(min_length=1)
    questions: list[str] = Field(default_factory=list)
    decisions: dict[str, str] = Field(default_factory=dict)

class Task(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,50}$")
    description: str
    depends_on: list[str] = Field(default_factory=list)
    files: list[str] = Field(min_length=1, description="Exact repository-relative files this coding task will create or modify; write targets only, not inspection inputs")

class Plan(StrictModel):
    revision: int = Field(ge=1)
    tasks: list[Task] = Field(min_length=1, max_length=20)
    risks: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    @model_validator(mode="after")
    def validate_dag(self):
        ids = [task.id for task in self.tasks]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate task IDs")
        pending = {task.id: set(task.depends_on) for task in self.tasks}
        if any(not deps.issubset(set(ids)) for deps in pending.values()):
            raise ValueError("Unknown task dependency")
        done = set()
        while pending:
            ready = [key for key, deps in pending.items() if deps <= done]
            if not ready:
                raise ValueError("Cyclic task dependency")
            for key in ready:
                done.add(key)
                del pending[key]
        return self

class FileChange(StrictModel):
    path: str
    before_sha256: str | None
    content: str | None  # None means an explicitly proposed deletion.

class ChangeSet(StrictModel):
    summary: str
    changes: list[FileChange] = Field(min_length=1, max_length=25)
    @model_validator(mode="after")
    def unique_paths(self):
        paths = [change.path for change in self.changes]
        if len(paths) != len(set(paths)):
            raise ValueError("Duplicate paths in change set")
        if sum(len(change.content or "") for change in self.changes) > 500_000:
            raise ValueError("Change set exceeds size limit")
        return self

class Review(StrictModel):
    approved: bool
    findings: list[str]
    summary: str

class Documentation(StrictModel):
    summary: str
    behavior: list[str]
    risks: list[str]

class TestResult(StrictModel):
    passed: bool
    returncode: int
    unit_tests: int = 0
    integration_tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    classification: str
    log_path: str
    duration_seconds: float

class ApprovalDecision(StrictModel):
    approval_id: str
    proposal_hash: str
    decision: Literal["approve", "reject"]
    actor: str = Field(min_length=1, max_length=100)
    reason: str = Field(default="", max_length=2000)

class PlanRevisionRequest(StrictModel):
    approval_id: str = Field(min_length=1)
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)
    plan: Plan

    @model_validator(mode="after")
    def require_identity_and_reason(self):
        if not self.actor.strip() or not self.reason.strip():
            raise ValueError("Plan revision requires an actor and a reason")
        return self

def sha256(content: str | bytes) -> str:
    return hashlib.sha256(content.encode() if isinstance(content, str) else content).hexdigest()

def digest(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
