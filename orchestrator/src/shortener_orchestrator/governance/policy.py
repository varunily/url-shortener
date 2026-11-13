from .paths import PolicyError, allowed_change
from ..models import ChangeSet, Plan

# Exact command profiles. LLMs never supply argv, flags, executables, or shell text.
COMMANDS = {
    "verify": ("mvn", "-B", "-ntp", "clean", "verify"),
    "unit": ("mvn", "-B", "-ntp", "test"),
}

def command(profile: str) -> tuple[str, ...]:
    if profile not in COMMANDS:
        raise PolicyError("Command profile is not allowlisted")
    return COMMANDS[profile]

def validate_plan(plan: Plan):
    for task in plan.tasks:
        for name in task.files:
            allowed_change(name)

def validate_changes(proposal: ChangeSet, allowed_files: list[str]):
    for change in proposal.changes:
        allowed_change(change.path, change.content is None)
        if change.path not in allowed_files:
            raise PolicyError(f"Patch changes a file outside its approved task: {change.path}")
    return {
        "schema_changes": [c.path for c in proposal.changes if "/db/migration/" in c.path],
        "deletions": [c.path for c in proposal.changes if c.content is None],
        "executes_generated_code": True,
        "command": list(COMMANDS["verify"]),
    }
