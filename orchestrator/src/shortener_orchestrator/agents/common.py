from pathlib import Path
import time
from uuid import uuid4
from ..tools.commands import Stopped
from ..tools.repository import inspect, worktree_diff
from ..governance.redaction import redact

class AgentContext:
    def __init__(self, settings, store, provider, runner):
        self.settings, self.store, self.provider, self.runner = settings, store, provider, runner

    def check_stop(self, state):
        if self.store.stopped(state["run_id"]):
            raise Stopped("Operator requested stop")

    def context(self, state, **extra):
        self.check_stop(state)
        context = dict(state)
        context["repository"] = inspect(Path(state["workspace"]))
        context.update(extra)
        errors = [event for event in self.store.events(state["run_id"]) if event["kind"] == "execution_error"]
        if errors:
            context["previous_execution_error"] = errors[-1]["data"]
        if state.get("test_result", {}).get("log_path"):
            path = Path(state["test_result"]["log_path"])
            if path.exists():
                context["failure_log_tail"] = redact(path.read_text()[-12000:])
        return context

    def invoke(self, state, agent, action):
        self.check_stop(state)
        invocation_id = uuid4().hex
        identity = f"{agent}:{state.get('revision', 1)}:{state.get('task_id', '')}:{invocation_id}"
        metadata = {"agent": agent, "task_id": state.get("task_id"),
                    "revision": state.get("revision", 1), "invocation_id": invocation_id}
        self.store.event(state["run_id"], "agent_started", metadata,
                         key=identity + ":started")
        started = time.monotonic()
        try:
            result = action()
        except Exception as error:
            self.store.event(state["run_id"], "agent_failed",
                             {**metadata, "error_type": type(error).__name__,
                              "duration_seconds": time.monotonic() - started}, key=identity + ":failed")
            raise
        outcome = "agent_failed" if getattr(result, "passed", True) is False else "agent_succeeded"
        self.store.event(state["run_id"], outcome,
                         {**metadata, "duration_seconds": time.monotonic() - started},
                         key=identity + ":" + outcome)
        return result
