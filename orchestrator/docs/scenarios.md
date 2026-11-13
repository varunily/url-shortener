# Scenario walkthroughs

All runs start from the recorded Git baseline in separate detached worktrees. Generated migrations operate only in disposable Testcontainers databases during verification; the running Compose database is not changed.

## Greenfield: custom aliases

Start with ./orchestrator/run run greenfield --provider fake.

Review and approve the generated plan. The dependency graph decomposes schema/entity changes, API/service changes, then regressions/documentation. The Coding Agent produces a concrete diff; it does not modify the worktree before patch approval.

The feature adds optional customAlias, length 3–32, Base62, case-sensitive uniqueness, 409 ALIAS_CONFLICT, and reserved-name rejection. Generated codes stay seven characters. V3 widens the column and check constraint. Regressions exercise redirect/stats/disable and competing creators.

After patch approval, Maven and static checks run, then review and documentation synchronize. Final readiness needs a human decision. The diff remains available for later manual integration.

## Brownfield: expiration archival

Start with ./orchestrator/run run brownfield --provider fake.

Inspection identifies that 410 / URL_EXPIRED already exists. The new work adds archived_at, a partial expiration index, a bounded transactional archival service, and a scheduled caller. The default batch is 100 rows, the interval and initial delay are 60 seconds, and row locking uses SKIP LOCKED.

The cleanup is archival, not deletion. Mappings, original URLs, click statistics, and 410 behavior are preserved. Disabled links retain URL_DISABLED precedence. Tests cover the exact expiration boundary, idempotence, unchanged active/permanent links, and concurrent bounded batches.

## Ambiguous request

Start with ./orchestrator/run run ambiguous --provider fake.

The request “Improve URL security and expiration” pauses before planning. A human supplies the scheme policy, maximum explicit expiration, and retention choice. FakeLLM's supported example is:

~~~json
{"url_policy":"http_https","max_expiration_days":30,"cleanup":"archive"}
~~~

Clarification is persisted with actor and timestamp, then the Requirement Agent runs again. It proceeds through the same plan, patch, validation, review, and readiness gates. The chosen maximum is reflected in the actual Java code and boundary tests. Unsupported offline policies fail clearly instead of being reinterpreted.

## Failure recovery demonstration

Start with ./orchestrator/run run retry_rollback --provider fake.

The fixture deliberately adds a Java test that fails. Every run/retry executes actual Maven when using the normal CLI runner. Each replan has a new revision and an auditable test result. After the initial attempt and three retries, the workflow pauses for rollback approval.

Approving rollback restores the run-owned files and verifies a clean diff against the baseline. Its terminal status is ROLLED_BACK, which counts as an unsuccessful workflow with successful recovery—not release readiness.

For a recoverable failure example, use run brownfield --provider fake --fault once. This is explicitly injected deterministic recovery, not a claim of autonomous model debugging.

## Acceptance evidence

A human demonstration is complete only when its run reaches READY or the expected ROLLED_BACK outcome after real operator decisions. Pytest's synthetic approval decisions are separate test evidence.

At any pause, inspect:
- manifest.json and pending approval payload
- plan.json and versioned plans
- changes/*.patch
- tests/*.log and tests/*.json
- audit.jsonl, approvals.jsonl, metrics.json

The three scenario worktrees are independent. Their V3 migrations require reconciliation before a combined merge. No workflow performs that merge automatically.
