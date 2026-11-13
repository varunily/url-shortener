# Architecture and state

Six agents share structured LangGraph state. Pydantic validates provider outputs. The graph—not the model—owns control flow, commands, approval verification, retry limits, and filesystem authority.

~~~mermaid
flowchart TD
    CLI[CLI / optional local FastAPI] --> S[Workflow service]
    S --> G[LangGraph StateGraph]
    G --> CP[(SQLite checkpoints)]
    G --> RA[Requirement agent]
    RA --> CL{Unresolved questions?}
    CL -->|Yes| CI[Clarification interrupt]
    CI --> RA
    CL -->|No| PA[Planning agent]
    PA --> PG[Plan approval interrupt]
    PG --> TS[Task dependency scheduler]
    TS --> CA[Coding agent: proposals]
    CA --> TS
    TS -->|All proposals ready| AP[Patch/schema/execution approval interrupt]
    AP --> W[Journaled application in Git worktree]
    W --> TA[Testing agent: Maven]
    W --> SC[Static scope checks]
    TA --> B[Validation barrier]
    SC --> B
    B -->|Pass| RV[Review agent]
    B -->|Pass| DA[Documentation agent]
    RV --> RB[Review barrier]
    DA --> RB
    RB --> RG[Release-readiness approval]
    RG --> E[Report and artifacts]
    B -->|Repairable failure| RP[Replan with failure evidence]
    RP -->|Retry budget available| PA
    B -->|Retries exhausted| RA2[Rollback approval]
    RA2 --> R[Restore and verify run-owned files]
    B -->|Environment/policy failure| STOP[Safe stop]
    G --> AUD[(SQLite audit and decisions)]
    AUD --> ART[Run folder and metrics]
~~~

## State model

WorkflowState contains run/thread identity, scenario/request, selected provider/model, baseline/worktree, requirements, human clarification, plan revision and task DAG, completed proposal tasks, pending file changes, approval decision outcome, applied diff hash, test/static/review/documentation results, retry count, recovery time, and terminal status.

Node updates use separate channels for parallel results, so testing and static checks do not overwrite each other. Review and documentation have a second independent fan-out/join barrier. Coding proposals follow actual dependency order; the scheduler rejects cyclic plans and unknown dependencies.

The Coding Agent proposes complete file operations with expected source hashes. Proposals remain in the run folder until a human authorizes the concrete consolidated patch. The operator approves schema changes and execution of generated Java as part of that patch's explicit scope.

## Persistence and replay

A run ID is LangGraph's thread_id. SQLite checkpoints persist node state and interrupts across process restarts. Approval nodes use interrupt() and require an approval decision already recorded in SQLite; a forged Command(resume=...) alone cannot grant authority.

A file journal is written before each mutation. Repeated application accepts the exact expected preimage or the already-applied approved result. Unknown file versions stop the workflow. Approval events use deduplication keys to avoid replay inflating decision history.

SQLite and filesystem changes are not one atomic transaction. Journaling and preimage reconciliation make replay safe; power-loss and external file corruption remain limits of the local prototype. Per-run file locks prevent concurrent CLI/API workers from executing the same run.

## Failure classification and recovery

Validation failures can trigger at most three repair retries after the initial attempt. Replanning creates a new plan revision, with actual Maven logs or review findings in the context. A revised plan and changed patch need new approvals.

Environment failures, timeouts, output overflow, policy violations, and unexpected execution errors stop safely instead of hiding the cause with code rewrites. Safe-stop controls are durable and checked at node boundaries and during Maven execution.

After retry exhaustion, rollback is another interrupt. Only after approval does it restore journaled originals, remove run-added files, and verify a clean worktree diff. External edits block rollback. It does not reset the root repository or undo a live database migration.

## Providers and evidence

FakeLLM is a deterministic fixture adapter. Its review reports explicitly say that no semantic model review happened. Ollama uses local qwen2.5-coder:7b with schema validation and zero temperature; no provider fallback is implicit.

The Testing Agent does not ask the model whether tests passed. It runs a fixed argv command and parses real XML reports. A green verification requires successful exit, both unit and integration test counts greater than zero, and zero failures, errors, or skipped tests.

References: [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [graph state and control flow](https://docs.langchain.com/oss/python/langgraph/graph-api), [Ollama structured output](https://docs.ollama.com/capabilities/structured-outputs).

## Project structure

The backend's src/, pom.xml, migrations, and existing build scripts stay at the repository root. The Phase 2 source tree is:

~~~text
orchestrator/
├── README.md
├── .env.example
├── pyproject.toml
├── requirements.lock
├── run
├── docs/
│   ├── architecture.md
│   ├── api-examples.md
│   ├── governance.md
│   ├── scenarios.md
│   ├── testing.md
│   └── validation-results.json
├── src/shortener_orchestrator/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── api.py
│   ├── config.py
│   ├── models.py
│   ├── service.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── requirement.py
│   │   ├── planning.py
│   │   ├── coding.py
│   │   ├── testing.py
│   │   ├── review.py
│   │   └── documentation.py
│   ├── workflow/
│   │   ├── __init__.py
│   │   ├── state.py
│   │   ├── graph.py
│   │   ├── scheduling.py
│   │   ├── gates.py
│   │   └── recovery.py
│   ├── governance/
│   │   ├── __init__.py
│   │   ├── paths.py
│   │   ├── policy.py
│   │   └── redaction.py
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── artifacts.py
│   │   ├── database.py
│   │   └── metrics.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── repository.py
│   │   ├── worktrees.py
│   │   ├── patches.py
│   │   ├── commands.py
│   │   └── test_reports.py
│   └── llm/
│       ├── __init__.py
│       ├── provider.py
│       ├── context.py
│       ├── fake.py
│       ├── fixtures.py
│       └── ollama.py
├── tests/
│   ├── conftest.py
│   ├── test_governance.py
│   ├── test_workflows.py
│   ├── test_observability.py
│   ├── test_commands.py
│   ├── test_ollama.py
│   ├── test_cli_api.py
│   └── test_maven_scenarios.py
├── .venv/          # ignored local dependencies
├── .state/         # ignored checkpoints/audit/locks
├── runs/           # ignored run artifacts
├── worktrees/      # ignored isolated source workspaces
└── .tmp/           # ignored disposable test runtimes
~~~

ORCHESTRATOR_RUNTIME_ROOT can select another runtime directory strictly inside this project's orchestrator folder. CLI acceptance tests use this to isolate their decisions and metrics from human demonstrations. The supported runtime is macOS/Linux (fcntl locks and process groups); native Windows needs equivalent platform adapters.
