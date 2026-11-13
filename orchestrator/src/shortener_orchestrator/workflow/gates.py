from langgraph.types import interrupt
from ..governance.paths import PolicyError

def plan_payload(state):
    payload = {"baseline": state["baseline"], "provider": state["provider"], "plan": state["plan"]}
    if state.get("plan_provenance"):
        payload["provenance"] = state["plan_provenance"]
    return payload

def approval(runtime, state, kind, payload):
    runtime.check_stop(state)
    record = runtime.store.approval(state["run_id"], kind, payload)
    response = interrupt({"kind": "approval", "approval_id": record["id"],
                          "proposal_hash": record["proposal_hash"], "action": kind, "payload": payload})
    if not isinstance(response, dict) or response.get("approval_id") != record["id"] \
            or response.get("proposal_hash") != record["proposal_hash"]:
        raise PolicyError("Resume payload does not match the pending approval")
    decision = runtime.store.approval_status(record["id"])
    if decision not in {"approve", "reject"}:
        raise PolicyError("An explicit persisted operator decision is required")
    return {"approval_granted": decision == "approve"}

def clarify(runtime, state):
    runtime.check_stop(state)
    response = interrupt({"kind": "clarification", "questions": state["requirements"]["questions"],
                          "run_id": state["run_id"]})
    if not isinstance(response, dict) or "answers" not in response:
        raise PolicyError("Clarification requires structured answers")
    answers = response["answers"]
    if state["provider"] == "fake":
        if answers.get("url_policy") != "http_https" or answers.get("cleanup") != "archive":
            raise PolicyError("Offline fixture supports http_https and archive only; use Ollama for another policy")
        days = answers.get("max_expiration_days")
        if type(days) is not int or not 1 <= days <= 365:
            raise PolicyError("max_expiration_days must be an integer from 1 to 365")
    if not response.get("actor"):
        raise PolicyError("Clarification requires an operator identity")
    runtime.store.event(state["run_id"], "clarified", response,
                        key="clarified:" + str(state["revision"]))
    return {"clarification": answers}
