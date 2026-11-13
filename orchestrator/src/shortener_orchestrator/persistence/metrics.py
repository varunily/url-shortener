import time

def calculate(run, events, approvals):
    agents = {}
    recoveries = []
    for event in events:
        data = event["data"]
        if event["kind"] in {"agent_succeeded", "agent_failed"}:
            count = agents.setdefault(data["agent"], {"success": 0, "failure": 0})
            count["success" if event["kind"] == "agent_succeeded" else "failure"] += 1
        if event["kind"] == "recovered":
            recoveries.append(data["duration_seconds"])
    end = run["finished"] or time.time()
    wait = sum(max(0, (row["decided"] or end) - row["created"]) for row in approvals)
    return {
        "status": run["status"],
        "elapsed_seconds": max(0, end - run["started"]),
        "approval_wait_seconds": wait,
        "agent_outcomes": agents,
        "retry_count": sum(event["kind"] == "replanned" for event in events),
        "rollback_count": sum(event["kind"] == "rolled_back" for event in events),
        "mean_time_to_recovery_seconds": sum(recoveries) / len(recoveries) if recoveries else None,
        "definition": "Recovery: first observed failure to passing validation or verified rollback; pending runs are not successes.",
    }
