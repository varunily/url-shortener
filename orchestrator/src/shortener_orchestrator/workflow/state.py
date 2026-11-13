from typing import TypedDict

class WorkflowState(TypedDict, total=False):
    run_id: str
    scenario: str
    request: str
    provider: str
    model: str
    baseline: str
    workspace: str
    status: str
    requirements: dict
    clarification: dict
    plan: dict
    plan_provenance: dict
    coding_feedback: dict
    applied_digest: str
    revision: int
    retry_count: int
    completed_tasks: list[str]
    task_id: str
    proposal: dict
    test_result: dict
    static_result: dict
    review: dict
    documentation: dict
    failure: dict
    recovery_started: float | None
    decision_ids: list[str]
    fault: str | None
    rollback_result: dict
    pending_changes: list[dict]
    task_proposal: dict
    approval_granted: bool
    applied_digest: str
