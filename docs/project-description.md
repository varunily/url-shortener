# Project Description

This document explains the URL Shortener assignment in plain language. Its seven main sections follow the assignment PDF: Objective, Scenario, Scope, Core Requirements, Deliverables, Evaluation Criteria, and Expectation.

## 1. Objective

The assignment asks for a working prototype that turns an engineering request into a reviewable result. The system should understand the request, break it into tasks, perform multiple steps, validate its output, and keep people in control of important decisions.

This repository contains two related parts:

1. A URL shortener application that acts as the system being changed.
2. A local engineering orchestrator that plans, proposes, tests, audits, and reports changes to that application.

The orchestrator can prepare and validate changes, but it does not merge or deploy them automatically. Human approval gates preserve operator control.

## 2. Scenario

The application scenario is a URL shortener with core APIs, click analytics, and reliability features. The assignment frames the work as a 2–3 day effort using AI assistance while demonstrating engineering judgment.

### URL shortener application

The backend is a Java 21, Spring Boot 3.5.4 application. It stores links and click events in PostgreSQL 16 and uses Flyway to manage schema changes. It provides:

- `POST /api/v1/urls` to create a short link.
- `GET /{code}` to record a click and redirect with HTTP 302.
- `GET /api/v1/urls/{code}` to read link information.
- `GET /api/v1/urls/{code}/stats` to read total and daily click counts.
- `PATCH /api/v1/urls/{code}/disable` to disable a link.
- A one-page HTML/CSS/JavaScript interface at <http://localhost:8080/>.

The current frontend accepts a long URL and an optional expiration from 1–30 days. It displays the short link, supports copying and opening it, and fetches click statistics. Custom aliases are not included in the root application.

### Agentic engineering orchestrator

The Python 3.11+ orchestrator uses LangGraph for workflow control, Pydantic for structured data, SQLite for checkpoints and audit records, and Git worktrees to isolate proposed code changes. The CLI is the primary interface; a small local FastAPI interface is optional.

The orchestrator has six agents: requirement, planning, coding, testing, review, and documentation. They share workflow state and evidence. The workflow pauses when an operator decision is needed, such as approving a plan, a concrete code patch, database changes, rollback, or final readiness.

## 3. Scope

The assignment covers:

- Greenfield scenarios: adding a new system or feature.
- Brownfield scenarios: improving or fixing existing code.
- Test and documentation improvements.
- Clear requirements and ambiguous requirements.

The demonstrations are:

| Scenario | Request and result | Evidence run |
|---|---|---|
| Greenfield | Add optional custom aliases, collision handling, a migration, and regression tests. | `34a6434bf2c9`, READY |
| Brownfield | Archive expired links while preserving the link mappings, click events, and existing `410 URL_EXPIRED` response. | `7a3c0bb800e2`, READY |
| Ambiguous requirement | Clarify “Improve URL security and expiration”; the recorded choices set a 30-day maximum expiration and archive data while preserving mappings and click statistics. | `2f72a083f296`, READY |

Each scenario was run in its own Git worktree. Its proposed changes remain reviewable there; they have not been merged into the root application. The greenfield custom-alias feature is therefore a demonstrated worktree scenario, not a feature of the current root API or frontend.

## 4. Core Requirements

### 1. Requirement Understanding

The system must understand intent, identify ambiguity, and make the engineering request clear. The Requirement Agent creates structured requirements and acceptance criteria. For the ambiguous scenario, the workflow pauses for human answers and records those answers before planning continues.

### 2. Task Decomposition

The system must turn large requests into smaller tasks with dependencies and an order of work. The Planning Agent produces a task dependency graph (DAG), which means tasks that depend on other tasks wait until those tasks are complete. The workflow can run independent checks in parallel and waits at synchronization points before proceeding.

### 3. Codebase Reasoning (Brownfield)

The system must find the affected parts of an existing project and understand how they work together. Plans identify impacted Java classes, endpoints, database migrations, tests, and documentation. The expiration archival scenario preserves the existing redirect and analytics behavior while adding scheduled archival and PostgreSQL regression coverage.

### 4. Workflow Orchestration (Critical Differentiator)

The system must coordinate the software lifecycle with a stateful, governed graph rather than a simple chain of prompts. LangGraph stores workflow checkpoints in SQLite. The graph preserves requirements, decisions, plans, approvals, patch state, test results, review, documentation, and metrics as work progresses.

The workflow includes sequential tasks, parallel checks and review/documentation paths, synchronization barriers, entry and exit gates, human approval checkpoints, bounded retries, recovery, rollback, and safe-stop handling. Commands are allowlisted; code changes are restricted to an isolated worktree and reviewed file scope. A changed plan or patch requires a new decision. The system records audit events and metrics such as run status, agent outcomes, retries, rollback count, approval wait, and elapsed time.

### 5. Engineering Output Generation

The project contains a working Java API, database migrations, tests, frontend, and supporting documentation. The Coding Agent proposes changes as reviewable patches. It does not directly make an unapproved proposal part of the worktree. After approval, the Testing Agent runs the allowed Maven command and parses actual test reports; the system does not rely on a model's claim that tests passed.

The orchestrator supports a deterministic FakeLLM for its documented fixtures and a local Ollama provider configured for `qwen2.5-coder:7b`. FakeLLM fixture output is not represented as real model inference.

### 6. Validation and Risk Control

Validation includes Java unit/HTTP tests and PostgreSQL Testcontainers integration tests. Orchestrator checks cover workflow state, approvals, persistence, policy, retries, and recovery. A failed Java validation may be retried up to three times after the initial attempt; rollback requires a separate human approval.

The design records trade-offs and limits. For example, click events are written synchronously to PostgreSQL, rate limits are in memory per application process, Phase 1 has no authentication, and functional tests do not prove production load capacity or deployment readiness.

### 7. Controlled Autonomy

The agents can perform multiple approved steps, but they cannot approve their own high-impact changes. A human reviews the plan, patch, schema and Maven scope, rollback request, and final readiness proposal at separate gates. The orchestrator does not automatically merge, commit, push, or deploy as part of a run.

### 8. Final Engineering Summary

Each workflow run records its request, plan, decisions, approvals, code diff, test results, audit history, metrics, review, and readiness report under `orchestrator/runs/<RUN_ID>/`. The run folder lets a reviewer see what was proposed, what was approved, what actually ran, and what result was recorded.

## 5. Deliverables

### Working prototype and setup

The backend and PostgreSQL can be started from the repository root:

~~~bash
docker compose up -d
docker compose ps
curl --fail http://localhost:8080/actuator/health/readiness
~~~

Open the UI at <http://localhost:8080/>. The orchestrator installation, provider setup, and CLI approval steps are in the [root README](../README.md) and [orchestrator README](../orchestrator/README.md).

### Architecture and key decisions

- [Backend components, data schema, and transaction flows](architecture.md)
- [Backend reliability, security, scalability, and trade-offs](design-decisions.md)
- [Orchestrator graph, state, and persistence](../orchestrator/docs/architecture.md)
- [Orchestrator security, approvals, and rollback controls](../orchestrator/docs/governance.md)

### Scenario evidence

The three assignment scenarios reached READY after their separate human approval gates and real Maven/PostgreSQL verification. The Ollama-backed brownfield run `d80be97dedbe` also reached READY with 62 unit/HTTP tests and 23 PostgreSQL integration tests. The scenario reports and audit data are local run artifacts and are not committed as runtime state.

### Testing approach and recorded results

On 2026-11-13, the root Java project passed `mvn clean verify`: **75 tests, 0 failures, 0 errors, and 0 skipped**. The run used Java 21 and PostgreSQL 16 Testcontainers.

The complete Python orchestrator suite passed **113 tests, 0 failures, 0 errors, 0 skipped, and 0 deselected**. It included four CLI acceptance scenarios that executed real Maven/Testcontainers validation in isolated worktrees. These totals describe separate suites and should not be added together as if they were one build.

### Issues encountered and how they were resolved

| Issue | How it was found | Resolution |
|---|---|---|
| The browser returned 404 at `/`. | The packaged static page existed, but Spring's welcome-page forwarding reached the existing single-segment redirect mapping for `/index.html`. | Added an explicit root controller that serves `static/index.html` directly. Restricted redirect and HEAD routes to seven-character Base62 codes. Regression tests now check `/`, `/index.html`, and real short-code redirects. |
| The custom-alias request was rejected. | The API's `CreateUrlRequest` does not contain `customAlias`, and strict JSON parsing rejects unknown properties. | Kept the backend contract unchanged for this frontend update and removed the custom-alias field from the UI. Expiration remains optional and is limited to 1–30 days by the frontend. |
| A Java version mismatch was found before the full regression. | Environment inspection showed the host default was Java 25, while Maven Enforcer in this project requires Java 21. | Installed and selected Java 21 for the full Maven and Python CLI acceptance suites. Both suites passed with Testcontainers enabled. |
| The original PostgreSQL host port was already occupied. | The first local Compose setup encountered an existing service using host port 5432. | Compose publishes this project's PostgreSQL on host port 5433 while the container continues listening on 5432 internally. |
| Model-generated implementation proposals needed engineering corrections. | Reviews caught an incorrect migration shape, unsupported entity/service methods, misplaced scheduling logic, and incomplete regression proposals before application. | Used recorded task-specific feedback and a controlled revised plan/patch process. Each corrected proposal received a new approval hash and was reviewed before application and Maven validation. |
| Different scenarios proposed separate Flyway V3 migrations. | Each scenario starts from the same baseline in an isolated worktree. | Kept scenario changes isolated and documented that their migrations must be reconciled before any combined integration. |

### Limitations and trade-offs

- The Phase 1 service does not require authentication.
- Click analytics use durable synchronous PostgreSQL writes; event storage grows over time.
- The creation rate limiter is in memory and applies per JVM.
- The orchestrator is a local prototype, not a distributed multi-user service.
- Scenario worktree changes are not automatically integrated into the root application.
- Functional and local concurrency tests do not establish a production capacity limit, security certification, or deployment readiness.

## 6. Evaluation Criteria

The assignment evaluates:

- Effectiveness of agentic orchestration.
- Architecture and system design quality.
- Depth of decomposition and execution quality.
- Realism and quality of generated outputs.
- Validation and risk-management rigor.
- Clarity and defensibility of decisions.
- Core engineering principles: modular, testable, reliable, secure, scalable code with safe change management.
- Engineering judgment.

Evidence is available in the architecture and governance documents linked above, the scenario walkthroughs at [orchestrator/docs/scenarios.md](../orchestrator/docs/scenarios.md), and the executed results at [orchestrator/docs/testing.md](../orchestrator/docs/testing.md).

## 7. Expectation

This project treats the assignment as production-grade engineering work: design fundamentals, lifecycle orchestration, ownership of outputs, and defensible reasoning. The operating principle is: **Agents execute under defined autonomy boundaries; humans own oversight, approvals, and final quality.**
