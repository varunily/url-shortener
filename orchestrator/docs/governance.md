# Governance and limitations

## Authority boundaries

The operator authorizes the plan, concrete patch, schema changes, execution of generated Java, rollback, and final readiness. Decisions include actor, exact proposal hash, scope, and timestamp. Changed proposals require new decisions. Replayed or mismatched decisions are rejected.

CLI/API actor names are local audit labels, not authenticated identities. The prototype trusts the local operator and filesystem owner. FastAPI binds to loopback and must not be exposed publicly without authentication, authorization, CSRF/origin review, and deployment hardening.

There is no auto-approval mode. Test fixtures explicitly simulate decisions; those results must not be called human-approved CLI demonstrations.

## Controlled plan revisions

`revise-plan` accepts a complete Plan and the exact currently pending plan approval
ID/hash, plus an actor and reason. It is limited to a clean worktree before coding
or patch application. It validates the next revision number, task DAG, allowed
paths, traversal/symlink restrictions, and file size. It rejects decided proposals,
later gates, stopped runs, and concurrent writers. Revisions have explicit
operator-supplied provenance rather than claiming a new model response.

The audit database atomically journals the request, marks the original approval
`superseded`, and sets `REVISING_PLAN`. The LangGraph checkpoint is updated through
`update_state(..., as_node="planning")`, then executes only the new plan gate.
The new approval binds the complete plan and provenance. After verifying that
interrupt, versioned artifacts are exported and the audit transaction records
`plan_revised` and `AWAITING_APPROVAL`. The original version remains available.
Both revision events are exported in decisions.jsonl. Manual plan revisions do
not count as automatic test-repair retries or model-agent invocations.

## Controlled patch revisions

At a pending patch gate only, `revise-patch` accepts the exact old approval ID and
full hash, an actor/reason, and a complete ChangeSet. It checks the unchanged
approved plan scope, all required files exactly once, current source hashes, clean
worktree, no application journal, and a changed rendered diff. It does not accept
decided approvals or later gates. The audit database journals the correction and
supersedes old authority atomically; the LangGraph checkpoint resumes through
`patch_gate` only, creating a fresh approval hash. A durable journal allows explicit
resume after interruption. Earlier patch bytes remain reviewable. No apply,
schema execution, or Maven operation happens during patch revision.

The audit database and checkpoint database have separate transactions. The durable
revision journal covers that boundary: interrupted registration blocks decisions,
and explicit resume idempotently finishes the journal, stopping at the new approval
gate. It never silently re-enables a superseded approval. Stop flags are honored;
recovery of a stopped operation requires explicit resume. Direct filesystem/database
tampering by the local owner remains outside the prototype's trust boundary.

## Commands and code execution

The model cannot provide shell commands. The command runner selects fixed profiles such as Maven clean verify, uses shell=False, strips application/provider credentials from the subprocess environment, bounds runtime and captured output, and terminates its own process group on stop/timeout.

POM files, Maven wrappers, Git metadata, old migrations, secret files, and orchestrator policy code are outside the model's writable scope. Scope checks and source hashes reject unexpected changes.

A Git worktree isolates source edits, not operating-system capabilities. Maven executes Java code and tests with the local user's permissions, and Testcontainers needs Docker access. An approved malicious test could still access host resources. Human patch review remains essential; hostile multi-tenant code requires a separate OS/container sandbox and constrained Docker broker. This prototype does not claim that shell=False alone solves that problem.

## File handling and rollback

Only canonical relative source/documentation paths are allowed. Traversal, absolute paths, hidden paths, symlinks, and writes outside the worktree are rejected. Existing V1/V2 migrations remain immutable. New migrations require the patch/schema approval.

All source changes are journaled before application. Rollback touches only recorded run-owned paths and refuses to overwrite external edits. It preserves failed diffs and evidence. Approval of rollback is not inferred from retry exhaustion.

The main backend tree remains unchanged. The sole commit authorized during implementation was the Phase 1 baseline. Workflows never commit, push, merge, or deploy. Test cleanup removes only disposable test-owned worktrees under orchestrator/.tmp.

## Prompt injection and secrets

Repository files and logs are labeled untrusted data in the Ollama system prompt. Structured schemas and tool-side policies enforce boundaries regardless of model instructions. Prompt wording is defense in depth, not the authority boundary.

Audit payloads and command logs redact common password/token/credential forms. Full arbitrary-secret detection is not guaranteed. Environment files and Git metadata are not given to the model. Source proposals and rollback journals contain source code and require the same confidentiality as the repository.

Provider availability and response errors are explicit. A failed Ollama call never becomes a claimed FakeLLM or successful model run.

## Metrics definitions

Per-run metrics derive from persisted events:
- Agent successes/failures count completed outcomes; failed validation counts as a Testing Agent failure.
- Each new agent invocation has its own ID, including repeated requirements/planning after resumption. Historical runs created before this correction may have deduplicated repeated calls within a revision; such records are retained rather than rewritten.
- Retry count counts replan transitions, bounded to three.
- Rollback count counts completed, verified rollback operations.
- Recovery time is elapsed time from first failed validation to passing validation or verified rollback.
- End-to-end duration includes human waiting; approval waiting is reported separately.
- Aggregate success rate is READY / (READY + FAILED + ROLLED_BACK + REJECTED). Pending/stopped runs are excluded, with a null rate when there are no terminal outcomes.

No workload means no invented success percentage or MTTR. SQLite/WAL and per-run process locks suit a local prototype; a distributed scheduler and authenticated approval service require a different deployment design.
