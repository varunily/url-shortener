from pathlib import Path
from .fixtures import all_changes, tasks
from ..models import sha256
from ..governance.paths import safe_path

class FakeLLM:
    """Deterministic fixtures; never represented as real inference."""
    def generate(self, agent, schema, context):
        if agent == "requirement":
            ambiguous = context["scenario"] == "ambiguous" and not context.get("clarification")
            value = {
                "summary": context["request"],
                "acceptance": ["Preserve existing backend regressions", "Maven executes PostgreSQL integration tests",
                               "Isolated worktree changes", "Human approvals precede high-impact actions"],
                "questions": ["Keep both HTTP and HTTPS?", "Maximum explicit expiration in days?",
                              "Confirm archival preserves mappings and statistics?"] if ambiguous else [],
                "decisions": {str(k): str(v) for k, v in context.get("clarification", {}).items()}}
        elif agent == "planning":
            value = {"revision": context["revision"], "tasks": tasks(context),
                     "risks": ["Schema migrations run only in disposable test databases",
                               "Maven executes approved Java; worktrees are not OS security sandboxes"],
                     "decisions": ["Preserve existing behavior", "No merges", "Archive without deleting data"]}
        elif agent == "coding":
            changes = all_changes(context)
            root = Path(context["workspace"])
            value = {"summary": "Offline fixture: " + context["task"]["description"],
                     "changes": [{"path": name, "before_sha256": sha256(path.read_bytes()) if path.exists() else None,
                                  "content": changes[name]} for name in context["task"]["files"]
                                 for path in [safe_path(root, name)]]}
        elif agent == "review":
            value = {"approved": context["test_result"]["passed"] and context["static_result"]["passed"],
                     "findings": [], "summary": "Offline review of actual diff and policy/test evidence. No semantic LLM review."}
        elif agent == "documentation":
            value = {"summary": "Scenario " + context["scenario"] + " using FakeLLM fixtures",
                     "behavior": context["requirements"]["acceptance"],
                     "risks": ["No real inference performed", "No merge or deployment performed"]}
        else:
            raise ValueError(f"Unknown fake agent: {agent}")
        return schema.model_validate(value)
