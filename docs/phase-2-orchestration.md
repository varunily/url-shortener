# Phase 2 orchestration

The local Python/LangGraph implementation now lives in [orchestrator/](../orchestrator/README.md) inside this repository. Phase 1 Java files remain in place and unchanged. The baseline is cb3e8c3440e3291b8a097dfb9483f37bebb05482, committed with varuntech0017@gmail.com.

The CLI drives six agents through structured requirements, dependency planning, concrete patch approval, isolated worktree changes, real Maven/PostgreSQL validation, parallel checks and review/documentation barriers, and a final readiness approval. SQLite stores checkpoints, decisions, audit events, and metrics. At most three retries follow the initial failed attempt; rollback requires its own decision and checks file ownership before restoration.

Demonstrations cover custom aliases, expiration archival preserving mappings/statistics, and clarification of an ambiguous security/expiration request. The implementation includes an explicit deterministic FakeLLM and a local Ollama adapter for qwen2.5-coder:7b. FakeLLM execution is never represented as real inference. Ollama was initially unavailable; it has since been installed, the requested model downloaded, and a real brownfield workflow started. See the current execution evidence in the Phase 2 test results.

- [Setup and exact CLI commands](../orchestrator/README.md)
- [Graph, state, and persistence](../orchestrator/docs/architecture.md)
- [Security, approval, and rollback boundaries](../orchestrator/docs/governance.md)
- [Scenario walkthroughs](../orchestrator/docs/scenarios.md)
- [Actual test results and pending demonstrations](../orchestrator/docs/testing.md)
- [Minimal loopback FastAPI interface](../orchestrator/docs/api-examples.md)

The orchestrator never automatically commits, merges, pushes, or deploys. A READY workflow means its reviewed worktree is ready for a separate integration decision. Synthetic test-operator approvals demonstrate protocol behavior; completing a human-operated interview demonstration still requires actual operator decisions at the persisted gates.
