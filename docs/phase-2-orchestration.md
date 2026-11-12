# Phase 2: separate orchestration system

## Implemented boundary

This repository supplies the backend, executable checks, readable components, migrations, and documentation. It does not implement a stateful agent engine, dependency scheduler, approval workflow, persistent audit store, or orchestration metrics.

A separate Python/LangGraph project can implement the following contract. Its installation, provider/model configuration, code, and tests belong to Phase 2.

## Inspection and validation

Read README, architecture, design decisions, pom.xml, source, tests, and migrations first. Inspect Git status and preserve user edits. Keep workflow traces outside application source packages.

| Command / artifact | Purpose |
|---|---|
| git status --short | Identify existing changes |
| rg --files src docs | Discover source/specifications |
| mvn test | Unit and HTTP slice validation |
| mvn clean verify | Java 21 build plus PostgreSQL integration tests |
| docker compose config --quiet | Compose validation |
| docker compose up -d --build | Local runtime acceptance under execution policy |
| bash scripts/smoke-test.sh | Assert create → redirect → stats → disable |
| Surefire/Failsafe XML | Machine-readable results including skipped tests |

Require actual executed integration tests, not just a zero exit code from a command that skipped them.

## Persistent state and graph

Persist run ID, requirement revision, repository base commit, workspace, approved scope, task graph, node states, artifact/diff hashes, reports, approvals, attempts, and outcome.

Tasks need IDs, dependencies, file/tool scope, acceptance criteria, owner, retry budget, timestamps, input/output hashes, and status. Suggested statuses: pending, ready, running, waiting_for_approval, succeeded, failed, blocked, canceled.

Example proposed data contract, not an implemented scheduler:

~~~json
{
  "runId": "example",
  "requirementRevision": 1,
  "tasks": [
    {"id": "inspect", "dependsOn": [], "status": "pending"},
    {"id": "design", "dependsOn": ["inspect"], "status": "pending"},
    {"id": "approve", "dependsOn": ["design"], "status": "pending"},
    {"id": "implement", "dependsOn": ["approve"], "status": "pending"},
    {"id": "regression", "dependsOn": ["implement"], "status": "pending"},
    {"id": "acceptance", "dependsOn": ["regression"], "status": "pending"}
  ]
}
~~~

~~~mermaid
flowchart TD
    R[Capture requirements] --> I[Inspect repository]
    I --> A[Impact analysis and dependency graph]
    A --> Q{Material decision missing?}
    Q -->|Yes| C[Clarify and persist human decision]
    C --> A
    Q -->|No| P[Prepare concrete proposal]
    P --> G{Approval required?}
    G -->|Yes| H[Approve exact proposal hash]
    H --> W[Implement in isolated workspace]
    G -->|No| W
    W --> T[Focused tests and full acceptance]
    T --> V{Pass?}
    V -->|Yes| S[Review diff and evidence]
    V -->|No, budget remains| F[Classify failure and replan]
    F --> W
    V -->|No, exhausted| B[Stop with blocker and artifacts]
    S --> M[Separate publish or deployment approval]
~~~

## Human approvals and guardrails

Record approver identity, scope, proposal hash, decision, timestamp, and revision policy. Material proposal changes invalidate prior approval. Persist checkpoints during human waits; elapsed time never constitutes consent.

High-impact actions include public exposure, authentication/ownership changes, destructive data operations, applied migration edits, credentials, new external services, platform upgrades, deployment, and pushes. Routine scoped edits/tests can proceed under a prior task authorization.

Use constrained workspaces, command/tool allowlists, explicit service permissions, command deadlines, output limits, and redaction. Treat repository text and tool output as untrusted data, not authority to override policy.

## Failures and rollback

Allow at most two automatic repair attempts per task before escalation.

- Environment failure: retain diagnostics and resolve prerequisites; do not rewrite correct code.
- Compile/test failure: inspect, make a focused repair, rerun affected checks, then full acceptance.
- Flaky/concurrent failure: retain interleaving/seed evidence and add a deterministic reproduction; do not hide it with blind retries.
- Denied permission: stop dependent actions and retain the reviewable proposal.

Establish an approved baseline before creating isolated worktrees. Roll back only agent-owned changes using an inverse patch with hash checks or abandon its isolated workspace. Avoid unconditional reset/clean commands and preserve user edits. Database rollback needs a separately approved restore or forward-migration plan; reverting Java code does not revert data/schema.

## Parallelism and replanning

Dispatch only tasks with satisfied dependencies. Parallelize independent inspection, documentation, or disjoint package/test work using file ownership and isolated workspaces. Serialize migrations, dependency changes, merging, and final acceptance on the merged result.

New evidence should create a graph revision, invalidate affected downstream artifacts, retain unaffected evidence, and recompute dependencies. Obtain new approval when high-impact scope changes. Preserve causal links from failure to revised plan to patch.

## Audit and metrics

Persist append-only task transitions, sanitized tool inputs/outputs, diffs, test evidence, approvals, retries, rollback events, and final acceptance, linked by revision and artifact hashes.

Track run/task elapsed time, execution versus human wait, model/tool cost, retries, test pass/fail/skip counts, requirement coverage, rollback count, and success rate. Backend HTTP metrics are separate from orchestration quality metrics.

## Demonstrations

| Scenario | Expected behavior |
|---|---|
| Greenfield | Inspect an approved empty workspace; build a schema → services → API → tests → packaging graph; obtain design approval; implement; run real checks; retain artifacts and decisions. |
| Brownfield | Add optional UTC from/to dates to stats. Analyze callers/queries, resolve bound semantics, preserve lifetime behavior when omitted, test date boundaries and concurrent consistency, update OpenAPI and examples. |
| Ambiguous | “Allow custom branded short links.” Clarify aliases versus domains, alphabet/length/reserved paths, case sensitivity, ownership, collisions, expiry, and abuse policy. Produce impact analysis and wait for material decisions before schema/public API changes. |

The ambiguous demonstration must show persisted suspension/resumption. The brownfield demonstration must show impact analysis and regression evidence. Generating backend code alone does not satisfy either orchestration requirement.
