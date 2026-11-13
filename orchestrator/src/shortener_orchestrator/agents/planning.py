from ..models import Plan
from ..governance.policy import validate_plan
from ..persistence.artifacts import write_json
from uuid import uuid4

def run(runtime, state):
    directory = runtime.store.directory(state["run_id"])
    def propose_and_validate():
        plan = runtime.provider.generate("planning", Plan, runtime.context(state))
        # Retain rejected model proposals for diagnosis without granting them authority.
        write_json(directory / "plans" / f"{state['revision']}-proposal-{uuid4().hex[:12]}.json", plan.model_dump())
        if plan.revision != state["revision"]:
            raise ValueError("Planner returned the wrong revision")
        validate_plan(plan)
        return plan
    plan = runtime.invoke(state, "planning", propose_and_validate)
    write_json(directory / "plan.json", plan.model_dump())
    write_json(directory / "plans" / f"{plan.revision}.json", plan.model_dump())
    return {"plan": plan.model_dump(), "plan_provenance": {}, "completed_tasks": [], "pending_changes": []}
