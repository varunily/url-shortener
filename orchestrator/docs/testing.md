# Verified results and remaining demonstrations

Validated on 2026-11-12 using macOS, Python 3.13.3, Java 21.0.13, Maven, Docker, and PostgreSQL Testcontainers. Baseline: cb3e8c3440e3291b8a097dfb9483f37bebb05482. [Machine-readable evidence](validation-results.json) records suite totals, run IDs, real Java results, metrics, and artifact locations.

## Executed verification

| Check | Actual result |
|---|---|
| Python governance, routing, persistence, approvals, API, timeout, and recovery suite | 58 passed, 4 Maven tests deselected |
| CLI acceptance suite, using separate processes and real Maven | 4 passed, 58 non-Maven tests deselected |
| Greenfield custom aliases | 59 unit/HTTP + 21 PostgreSQL integration = 80; zero failures/errors/skips |
| Brownfield expiration archival | 59 unit/HTTP + 19 PostgreSQL integration = 78; zero failures/errors/skips |
| Ambiguous policy after a synthetic clarification | 59 unit/HTTP + 21 PostgreSQL integration = 80; zero failures/errors/skips |
| Deliberate persistent Java test failure | Four real Maven attempts; each ran 60 unit/HTTP tests with exactly one expected failure; three retries, then verified rollback |

The deliberate failure stops Maven before integration tests. Its zero integration count is explicitly recorded, and none of these four failing Java executions is reported as a passing build. The outer Pytest acceptance test passes because the expected retry limit, approval gate, rollback, and audit outcomes were observed.

Every successful scenario executed mvn -B -ntp clean verify in its own Git worktree. Testcontainers ran successfully; these were actual PostgreSQL tests, not skipped or mocked. The Python unit suite uses execution doubles where appropriate; the CLI acceptance suite uses the actual command runner.

The tests cover forged approval resumes, wrong hashes/replayed decisions, restart with a persisted decision, parallel synchronization, maximum retries, external edits blocking rollback, stop/resume, concurrent worker locks, timeout termination, secret filtering, missing test reports, new-file diff coverage, and unavailable Ollama without fallback.

## Exact commands executed

~~~bash
PYTHONPATH=orchestrator/src orchestrator/.venv/bin/python -m pytest \
  orchestrator/tests -m 'not maven' --basetemp=orchestrator/.tmp/pytest \
  --junitxml=orchestrator/.state/pytest-unit.xml

JAVA_HOME='/private/tmp/jdk-21.0.13+9/Contents/Home' \
PYTHONPATH=orchestrator/src orchestrator/.venv/bin/python -m pytest \
  orchestrator/tests -m maven --basetemp=orchestrator/.tmp/pytest-maven \
  --junitxml=orchestrator/.state/pytest-maven.xml
~~~

The implementation session also captured stdout/stderr to orchestrator/.state/pytest-unit.log and pytest-maven.log. Elapsed times were 18.21 seconds and 85.20 seconds respectively. Docker and Git metadata access required execution outside the editor's filesystem sandbox.

## CLI evidence and approval provenance

The following completed CLI runs used deterministic FakeLLM and explicitly labeled **pytest-simulated-operator** decisions. They prove the CLI/state/persistence/test/rollback integration. They are not claimed as real human-approved demonstrations or Ollama inference.

| Scenario | Run | Outcome | Evidence folder |
|---|---|---|---|
| Greenfield | 35dc362c25af | READY | [artifacts](../.tmp/pytest-maven/test_real_maven_scenario_from_0/runtime/runs/35dc362c25af/) |
| Brownfield | 038aba2ddf5a | READY | [artifacts](../.tmp/pytest-maven/test_real_maven_scenario_from_1/runtime/runs/038aba2ddf5a/) |
| Ambiguous | 89b430cedba4 | READY | [artifacts](../.tmp/pytest-maven/test_real_maven_scenario_from_2/runtime/runs/89b430cedba4/) |
| Retry/rollback | d02c3d90c7a2 | ROLLED_BACK | [artifacts](../.tmp/pytest-maven/test_real_maven_scenario_from_3/runtime/runs/d02c3d90c7a2/) |

Each runtime folder also contains cli-transcript.jsonl. Each run includes audit.jsonl, approvals.jsonl, metrics.json, plans, proposed/applied diffs, and real test logs/results. Disposable test worktrees were removed by the test fixture after verification; evidence remains until the test temporary directory is reused. validation-results.json retains the measured summary.

## Human-operated run results

These separate runs retain their worktrees and checkpoints under orchestrator/runs and orchestrator/worktrees:

| Run | Scenario | Current gate |
|---|---|---|
| 34a6434bf2c9 | Greenfield | READY; final readiness approved, report complete, 80 Java tests passed |
| 7a3c0bb800e2 | Brownfield | READY; final readiness approved, report complete, 78 Java tests passed |
| 2f72a083f296 | Ambiguous | READY; final readiness approved, report complete, 80 Java tests passed |

After explicit chat decisions were recorded with actor varun, all three runs executed real Maven clean verify with Java 21 and PostgreSQL Testcontainers. Greenfield passed 59 unit/HTTP and 21 integration tests; brownfield passed 59 unit/HTTP and 19 integration tests; ambiguous passed 59 unit/HTTP and 21 integration tests. All had zero failures, errors, skipped tests, and retries. Their original worktrees now contain the approved changes, and their run folders retain the command logs, XML-derived results, review, audit, and metrics. These operator decisions are distinct from the earlier synthetic test approvals. Final readiness was explicitly approved for all three runs; their release-readiness.md reports are complete. No merge or deployment was authorized or performed.

The ambiguous run records HTTP/HTTPS support, a maximum explicit expiration of 30 days, and archival preserving mappings and click statistics. Its plan and concrete patch were explicitly approved, the patch was applied, and real Maven verification passed. Its final readiness decision is recorded with actor varun, and its final report is complete. The earlier validation report remains available alongside the final report.

No human approval was inferred from the project's implementation authorization. Inspect these runs with ./orchestrator/run inspect RUN_ID. The requested plan/patch/schema/execution, rollback, and final-readiness decisions must be supplied explicitly. A paused run is not counted as a successful workflow.

Concrete read-only patch previews are prepared for [greenfield](../runs/34a6434bf2c9/changes/1.patch) and [brownfield](../runs/7a3c0bb800e2/changes/1.patch), with scope and prospective hashes in each run's preview.json. These previews were generated without advancing the checkpoint, recording approval, or modifying either worktree. The normal workflow regenerates the proposal after plan approval; any later patch approval must match its actual hash.

## Unverified or deliberately limited

- Ollama was unavailable during the initial FakeLLM demonstrations. It has since been installed and real local inference has executed; the real-provider workflow described below remains separate from the completed FakeLLM demonstrations. A complete Ollama workflow through code, Maven, and final readiness is still required for full real-provider acceptance.
- A real small-model workflow can fail structured output, context, or code-quality checks. Such failures stop visibly; FakeLLM does not replace the selected provider automatically.
- All three human-operated demonstrations are READY with recorded operator decisions. They used FakeLLM; automated synthetic approvals and real Ollama inference are separate from these human-operated results.
- Worktrees isolate source changes, not host execution privileges. Generated Java executes only after patch/execution approval; see [governance](governance.md).
- Main backend Java/configuration files remain unchanged. Independent V3 migrations need reconciliation before any combined integration. No Phase 2 commit, merge, push, deployment, or production database migration was performed.
- Native Windows and production multi-user/distributed operation were not tested.

## Real Ollama execution

Ollama 0.40.16 was installed with Homebrew at the operator's request. The requested qwen2.5-coder:7b model was downloaded successfully (model ID dae161e27b0e, approximately 4.7 GB). The server runs on 127.0.0.1:11434. The workstation has 8 GB of memory; local requests use 8192 context tokens with a bounded input selection and a 300-second model-call timeout.

The CLI now accepts --model and persists the chosen model for subsequent resume operations. New regression tests cover explicit model selection, rejection of misleading model labels for FakeLLM, persisted model selection, bounded whole-file context, clarification follow-ups, timeout configuration, rejected-plan preservation, policy feedback during resumption, revision constraints, and distinct agent invocation counts. The initial Ollama-related Python regression run passed 70 tests, with four Maven acceptance tests deselected, in 21.45 seconds. The latest suite including controlled plan revision is recorded below; its XML/log replace the earlier regression output. These are Python checks, not a claim that the real model's Java implementation has passed Maven.

Real brownfield run: d80be97dedbe. The run used Ollama directly and produced structured requirement responses. It asked about schedule, retention, and regression coverage; those answers were reused from the already approved brownfield run 7a3c0bb800e2, with that provenance recorded in the clarification. A follow-up initially repeated answered questions, so the provider context was corrected to re-evaluate the original request with operator answers instead of echoing the previous draft. The saved run was resumed after that correction.

After the foreground server stopped, the workflow entered SAFE_STOPPED on a connection error. The local service was restored with brew services run ollama, which does not register login startup. The same checkpoint was resumed. Planning then safely rejected a protected pom.xml proposal and a mismatched revision; validator feedback and a revision-constrained response schema enabled a permitted five-task proposal.

The operator registered and approved the corrected T1-T7 plan after the [plan review](../runs/d80be97dedbe/plan-review.md). The run has since reached its patch gate. The generated Java draft has not been applied or verified with Maven; the patch review below identifies blockers. Historical agent counters in this run may undercount repeated calls made before the invocation-ID correction; the original audit records are preserved.

The run's manifest and inspect output are authoritative for its current checkpoint. No approval from a completed FakeLLM run is automatically granted to a new model-generated plan or patch. Artifacts are under orchestrator/runs/d80be97dedbe, including ollama-environment.json and audit.jsonl. No real-provider Java test success or final readiness is claimed until those stages execute.

## Controlled plan revision verification

On 2026-11-12, the Python regression suite passed **90 tests**, with **4 Maven
acceptance tests deselected**, in **19.43 seconds**. It includes 20 new revision
checks for exact-hash supersession, old resume payload rejection, DAG/path validation,
operator identity/reason, revision sequencing, dirty worktrees, later gates, locks,
explicit decisions, CLI/API behavior, atomic journal failure, and process interruption
before/after checkpoint update and after the new gate. Restart recovery invoked no
model or Maven and paused for a fresh approval. Synthetic approvals were used only
inside isolated tests. Evidence: `.state/pytest-ollama-regression.xml` and `.log`.

Executed command:

~~~bash
PYTHONPATH=orchestrator/src orchestrator/.venv/bin/python -m pytest orchestrator/tests \
  -m 'not maven' --basetemp=orchestrator/.tmp/pytest-ollama-regression \
  --junitxml=orchestrator/.state/pytest-ollama-regression.xml
~~~

The real CLI then registered revision 2 for d80be97dedbe without recording any
approval. Original plan approval `d80be97dedbe:plan:7e077572fe0fc372` is superseded.
New approval `d80be97dedbe:plan:14c3c0ca2a015598` is pending. The new plan has explicit
operator-supplied/Codex-review provenance; no fresh Ollama response is claimed for
this revision. `plans/1.json` is preserved, and `plans/2.json`, its revision provenance,
audit/decision events, manifest, and LangGraph interrupt agree. The Java worktree
remains clean, retry_count is 0, and no coding/testing agent has run in this scenario.

## Real Ollama patch generation and blocked approval recommendation

After explicit operator approval of revision 2, real Ollama calls generated all
seven task proposals. The original plan remains superseded. Early model output
attempted an out-of-task test change, which policy blocked; subsequent engineering
feedback corrected migration/service/scheduler drafts before consolidation.

The latest Python regression suite passed **98 tests**, with **4 Maven tests
deselected**, in **20.07 seconds**. It includes source-path/hash constraints,
rejected-proposal evidence, an initial coding attempt plus at most three retries
per task/revision, controlled rework of unapplied dependants, complete selected
reference files, and preservation of pure environment-variable references during
secret redaction. Evidence remains in `.state/pytest-ollama-regression.xml` and
its matching log. Earlier counts above are historical runs, not additive totals.

On 2026-11-13, run d80be97dedbe was inspected at pending patch approval
`d80be97dedbe:patch:b629d8cd2b5efad5`. It proposes 12 files. The worktree is clean,
all source hashes match, and there are zero changes_applied events or Testing Agent
calls. No patch/schema/Maven approval has been granted.

The [pre-approval engineering review](../runs/d80be97dedbe/patch-review.txt)
recommends revising this draft. Static inspection found missing imports, nonexistent
APIs in tests, the unchanged V1/V2 migration assertion, an unwanted scheduler
transaction, and incomplete/invalid regressions. A read-only `git apply --check`
failed with exit 128 because the diff renderer concatenated a missing-final-newline
file with the next header. This is a real model-produced draft with known defects,
not a passing Java implementation. The pending patch and its hash are retained;
corrections require a fresh governed proposal before approval and execution.

The pending draft was revised through `revise-patch`. The original patch approval
`d80be97dedbe:patch:b629d8cd2b5efad5` is superseded. Revision testing passed 11
checks covering renderer validity, exact pending-hash binding, invalid scopes and
dirty sources, no-op rejection, prior decisions, and recovery around journal,
checkpoint, and gate boundaries. A full Python suite passed 108 tests before the
final no-op test was added; 4 Maven tests were deselected. The renderer plus
revision-focused suite then passed 11 tests. Maven was not run.

The new pending patch approval is `d80be97dedbe:patch:635cd6e2a0980a38` with
proposal hash `635cd6e2a0980a38f949b205f69bd8891943353d38d1c2996ba64993ae30477d`.
Its actual registered diff passed read-only `git apply --check`. It contains 12
files. The main Java worktree remains clean; the patch has not been applied and
Maven/Testcontainers have not run. See [current patch revision review](../runs/d80be97dedbe/revised-patch-review.txt).
