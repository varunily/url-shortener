# Agentic engineering orchestrator

A local Python/LangGraph system that inspects the existing Java backend, proposes real changes, waits for human decisions, applies approved changes in Git worktrees, executes Maven, reviews actual diffs, and exports evidence.

The CLI is the primary interface. FastAPI is a small optional wrapper. This is Phase 2 in the same Git repository; the Java application remains in its original location.

## Prerequisites and setup

Python 3.11+ (tested on 3.13), Git, Java 21, Maven, and running Docker for PostgreSQL Testcontainers. macOS/Linux are supported; the process locks and process-group controls are Unix-specific.

From the repository root:

~~~bash
mkdir -p orchestrator/.cache orchestrator/.tmp
export PIP_CACHE_DIR="$PWD/orchestrator/.cache"
export TMPDIR="$PWD/orchestrator/.tmp"
python3 -m venv orchestrator/.venv
orchestrator/.venv/bin/python -m pip install -r orchestrator/requirements.lock
orchestrator/.venv/bin/python -m pip install -e 'orchestrator[test]'

# Select a durable JDK 21 installation, or the existing temporary validation JDK:
export JAVA_HOME='/private/tmp/jdk-21.0.13+9/Contents/Home'
./orchestrator/run doctor
~~~

The launcher explicitly sets the source import path, so it also works in environments that suppress editable-install .pth files. All paths are passed to subprocesses as argument arrays; spaces in this repository name are supported.

The initial Git baseline is cb3e8c3440e3291b8a097dfb9483f37bebb05482, authored with varuntech0017@gmail.com. New runs record the current committed HEAD as their baseline. Worktrees are detached and never automatically committed, merged, pushed, or deployed.

## LLM providers

The default is the explicitly labeled **FakeLLM** provider. Its deterministic fixtures support these demonstration scenarios, not arbitrary engineering requests. It still uses the real graph, checkpoints, approvals, worktrees, patch application, Maven commands, and test-report parsing.

Ollama mode uses **qwen2.5-coder:7b** with JSON-schema responses validated by Pydantic. The initial workstation inspection found no Ollama executable or listening API; it has since been installed with Homebrew and the model downloaded. Current execution evidence is recorded in [test results](docs/testing.md).

On macOS, install and run the local server in the background:

~~~bash
brew install ollama
brew services run ollama
~~~

From the project root:

~~~bash
ollama list
ollama pull qwen2.5-coder:7b
./orchestrator/run doctor
./orchestrator/run run brownfield --provider ollama --model qwen2.5-coder:7b
~~~

The provider does not fall back to FakeLLM if Ollama fails. Requirements, plans, code proposals, reviews, and documentation come from the selected provider; testing always uses deterministic command execution and real reports. Unavailable Ollama is recorded as a failed preflight with audit/metrics artifacts.

The --model flag overrides OLLAMA_MODEL for a new Ollama run. The selected model is saved with that run and retained on resume. Coding requests use a 16384-token context and a 4096-token output limit; other agents use 8192/2048. Coding retains complete target files, selected baseline references, and production outputs of upstream tasks. Non-production dependency outputs are indexed rather than copied into every later prompt. Human clarification and the approved current task remain explicit. Oversized required inputs fail instead of being truncated. Coding prompts are capped at 32000 JSON characters; other agents at 18000. Larger coding requests can be slow on this workstation's 8 GB of memory.

Model calls have a 300-second timeout, configurable through ORCHESTRATOR_LLM_TIMEOUT. The local server must remain running while a workflow uses it. The brew services run command keeps the server running independently of the terminal without registering startup at login; run it again after a reboot. A foreground alternative is OLLAMA_HOST=127.0.0.1:11434 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve.

## Human-controlled CLI workflow

~~~bash
./orchestrator/run run greenfield --provider fake
./orchestrator/run inspect RUN_ID
~~~

A new run pauses at plan approval and prints the approval ID, proposal hash, scope, and artifact paths. Review the plan, then explicitly approve and resume:

~~~bash
./orchestrator/run approve RUN_ID \
  --approval-id 'ID_FROM_INSPECT' \
  --proposal-hash 'HASH_FROM_INSPECT' \
  --actor 'varun'
./orchestrator/run resume RUN_ID
~~~

Approval only records a decision. Resume executes the graph until its next checkpoint. The next pause presents a concrete patch including migration changes and the approved Maven command. Approve that exact patch separately. After real tests and review pass, a final readiness gate pauses again. Approval never merges changes.

To correct an undecided plan before any coding, save a complete Plan JSON inside
the project with its revision incremented by exactly one, then run:

~~~bash
./orchestrator/run revise-plan RUN_ID \
  --plan-file orchestrator/runs/RUN_ID/corrected-plan.json \
  --approval-id 'CURRENT_PLAN_APPROVAL_ID' \
  --proposal-hash 'CURRENT_PLAN_FULL_HASH' \
  --actor varun --reason 'Correct dependencies, write scope, and acceptance criteria'
~~~

This supersedes the old approval and registers a new plan interrupt; it does not
approve anything, invoke the LLM, generate a patch, or run Maven. The output shows
the full new payload and approval hash. Only approve the new proposal after review.
The original plan and audit history are preserved. A clean worktree, a valid task
DAG, allowed paths, and an undecided plan gate are required. Operator-supplied
revisions are labeled separately from model output. They do not consume a test
repair retry. Rejecting a plan remains a terminal decision, not a revision request.

If interrupted during registration, the run remains REVISING_PLAN and all approval
decisions are blocked. `./orchestrator/run resume RUN_ID` completes the saved
revision and pauses at its new plan gate. Repeating the exact revision request also
recovers it unless the run has been stopped; a stopped run requires explicit resume.
Editing plan.json alone never changes checkpoint authority.

After a patch approval gate pauses, revise the complete ChangeSet proposal with:

~~~bash
./orchestrator/run revise-patch RUN_ID \
  --proposal-file orchestrator/runs/RUN_ID/corrected-patch.json \
  --approval-id 'CURRENT_PATCH_APPROVAL_ID' \
  --proposal-hash 'CURRENT_PATCH_FULL_HASH' \
  --actor varun --reason 'Address review findings'
~~~

This journals the replacement, supersedes the prior patch approval, and pauses
at a fresh patch/schema/Maven gate. It requires a clean worktree and exact source
hashes for all approved plan files. The operation cannot revise an already
decided gate, apply code, or execute Maven. The previous patch artifact is kept.

Before a patch gate is reached, a stopped coding run can receive review feedback
and regenerate an unapplied task plus its dependants under the same approved plan:

~~~bash
./orchestrator/run rework-coding RUN_ID --task-id TASK_ID \
  --feedback-file orchestrator/runs/RUN_ID/review-feedback.txt --actor reviewer
./orchestrator/run resume RUN_ID
~~~

This operation records feedback and invalidated tasks, retains earlier proposal
attempts, and requires an unchanged approved plan and clean worktree. It cannot
bypass a pending patch gate or modify applied code. Each coding task is limited to
an initial generation plus three retries per plan revision. Review corrections and
model failures are not permissions to apply code or execute Maven.

Use the same pattern for other scenarios:

~~~bash
./orchestrator/run run brownfield --provider fake
./orchestrator/run run ambiguous --provider fake
./orchestrator/run run retry_rollback --provider fake
~~~

The ambiguous scenario first requests clarification. Example human answer:

~~~bash
./orchestrator/run clarify RUN_ID --actor varun \
  --answers-json '{"url_policy":"http_https","max_expiration_days":30,"cleanup":"archive"}'
~~~

This answer is illustrative, not an automatically selected decision. FakeLLM supports keeping HTTP/HTTPS, a maximum explicit expiration of 1–365 days, and archival. Other policies need Ollama or an explicitly extended fixture.

Controls:

~~~bash
./orchestrator/run reject RUN_ID --approval-id ID --proposal-hash HASH --actor varun --reason 'Needs changes'
./orchestrator/run stop RUN_ID
./orchestrator/run resume RUN_ID
./orchestrator/run metrics
~~~

There is no auto-approve option. Runtime approvals are separate from the project implementation approval. Automated tests simulate operator decisions only inside isolated test fixtures.

## Scenarios

| Scenario | Actual changes |
|---|---|
| Greenfield | Optional 3–32-character Base62 custom aliases, reserved-name rejection, 409 collisions, V3 migration, full lifecycle and concurrent-alias tests |
| Brownfield | Scheduled bounded archival with archived_at and a partial index, preserving 410/URL_EXPIRED, mappings, statistics, and disabled precedence |
| Ambiguous | Clarification pause, then the agreed maximum expiration policy, security regressions, and archival |
| Retry/rollback | Explicit failing Java test; initial attempt plus at most three repair retries; approval required before restoring the baseline |

Brownfield archival is lifecycle bookkeeping; it deliberately does not delete data or reduce storage. Every scenario starts independently from the baseline. Their V3 migrations must be reconciled before any future combined merge.

## Artifacts and state

- orchestrator/.state/checkpoints.sqlite: LangGraph checkpoints.
- orchestrator/.state/audit.sqlite: runs, operator decisions, and append-only application events.
- orchestrator/worktrees/RUN_ID/: isolated Java changes.
- orchestrator/runs/RUN_ID/: manifest, requirements, versioned plans/proposals, patches, audit, approvals, test logs/results, metrics, review, and readiness report.

Artifacts exist while a run is paused or failed. The manifest is authoritative for workflow status; an artifact's existence alone is not success. Raw source journals are local rollback artifacts and should be treated as repository-confidential.

## Tests

~~~bash
PYTHONPATH=orchestrator/src orchestrator/.venv/bin/python -m pytest \
  orchestrator/tests -m 'not maven' --basetemp=orchestrator/.tmp/pytest

JAVA_HOME='/private/tmp/jdk-21.0.13+9/Contents/Home' \
PYTHONPATH=orchestrator/src orchestrator/.venv/bin/python -m pytest \
  orchestrator/tests -m maven --basetemp=orchestrator/.tmp/pytest-maven
~~~

The first group uses deterministic execution doubles for orchestration behavior. The second executes full Maven verification and real PostgreSQL Testcontainers for each scenario. Test approvals are labeled synthetic and are not human demonstration evidence.

[Architecture](docs/architecture.md), [governance](docs/governance.md), [scenario walkthroughs](docs/scenarios.md), [API examples](docs/api-examples.md), and [test results](docs/testing.md) explain behavior and limitations.

## Optional minimal API

~~~bash
./orchestrator/run serve --port 8090
~~~

This binds to 127.0.0.1. OpenAPI is at http://127.0.0.1:8090/docs. Operations use the same service/checkpoints as CLI. Execution requests block until a gate or completion; use the CLI for the primary demo. There is no remote multi-user authentication model; do not expose this prototype publicly.
