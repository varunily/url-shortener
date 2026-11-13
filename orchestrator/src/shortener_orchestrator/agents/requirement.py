from ..models import Requirements
from ..persistence.artifacts import write_json

def run(runtime, state):
    result = runtime.invoke(state, "requirement",
        lambda: runtime.provider.generate("requirement", Requirements, runtime.context(state)))
    # This scenario requires human clarification regardless of a model's confidence.
    if state["scenario"] == "ambiguous" and not state.get("clarification") and not result.questions:
        result.questions = ["Specify accepted URL schemes, maximum explicit expiration, and archival retention policy."]
    write_json(runtime.store.directory(state["run_id"]) / "requirements.json", result.model_dump())
    return {"requirements": result.model_dump()}
