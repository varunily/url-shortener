# Architecture

One Spring Boot process and one PostgreSQL database serve the complete Phase 1 API.

~~~mermaid
flowchart TD
    C[Client] --> R[Request ID filter]
    R --> L[Creation rate limit filter]
    L --> H[Controllers and DTO validation]
    H --> U[UrlService]
    H --> D[RedirectService]
    H --> A[AnalyticsService]
    U --> UR[UrlRepository]
    D --> UR
    D --> CR[ClickEventRepository]
    A --> UR
    A --> CR
    UR --> DB[(PostgreSQL 16)]
    CR --> DB
    F[Flyway migrations] --> DB
    H --> E[ApiExceptionHandler]
    E --> P[Problem Details]
~~~

## Responsibilities

| Package | Responsibility |
|---|---|
| controller | Routes, HTTP status/headers, validation, OpenAPI |
| service | Code allocation, lifecycle rules, transactional redirects |
| repository | JPA persistence, locking queries, PostgreSQL inserts |
| entity | Persistence state and effective lifecycle status |
| dto / mapper | Stable API records and response mapping |
| analytics | Snapshot aggregation and UTC daily statistics |
| exception | Stable error codes and sanitized Problem Details |
| configuration | Clock, public origin, scheduling, OpenAPI |
| validation | HTTP(S) syntax and input safeguards |
| web | Request IDs and in-memory creation throttling |

Constructor injection makes dependencies explicit. Interfaces define meaningful boundaries: persistence, short-code generation, and projections. The services stay concrete. This is one application with no extra deployment boundaries.

## Database

~~~mermaid
erDiagram
    urls ||--o{ click_events : records
    urls {
        bigint id PK
        varchar short_code UK
        varchar original_url
        timestamptz created_at
        timestamptz expires_at
        boolean disabled
    }
    click_events {
        bigint id PK
        bigint url_id FK
        timestamptz accessed_at
    }
~~~

V1 creates urls with an identity key, case-sensitive unique code, alphabet/length check, and expiration-after-creation check. V2 creates click_events with its foreign key and composite (url_id, accessed_at) index. Flyway owns the schema; Hibernate validates it.

Only disabled is mutable. Effective expiration is derived at read time and needs no scheduler. Disabled takes precedence over expired. The API never physically deletes records.

## Transactions

**Creation:** A write transaction uses targeted ON CONFLICT (short_code) DO NOTHING. Zero inserted rows means retry. Six failed candidates exhaust the policy. A uniqueness collision does not abort the PostgreSQL transaction; unrelated failures propagate. A successful mapping is read and returned after commit.

**Redirect:** Select the mapping with PESSIMISTIC_READ, which PostgreSQL implements with a shared row lock. After acquiring the lock, check lifecycle status and current time, insert one event, and commit before constructing 302.

**Disable:** Select with PESSIMISTIC_WRITE, set disabled, and commit. Exclusive locking waits for already admitted redirects. Redirects beginning after disable commits observe disabled state. An earlier in-flight HTTP response can still reach its client after disable because transaction ordering and network delivery are separate.

**Stats:** A read-only REPEATABLE READ transaction reads metadata, total/max time, and daily aggregates from one snapshot. Concurrent writes cannot make the daily sum disagree with the returned total.

~~~mermaid
sequenceDiagram
    participant Client
    participant Controller
    participant Service as RedirectService
    participant DB as PostgreSQL
    Client->>Controller: GET /abc1234
    Controller->>Service: redirect(code)
    Service->>DB: SELECT mapping FOR SHARE
    Service->>Service: Check disabled and expiration
    Service->>DB: INSERT click_events
    Service->>DB: COMMIT
    Service-->>Controller: Original URL
    Controller-->>Client: 302 + Location + no-store
~~~

A failed insert/commit produces 503 and no redirect. A client disconnect after commit can still leave an event; exactly-once network delivery is not promised.

## Observability

Requests get server-generated X-Request-Id values. JSON logs contain route templates, method, status, and duration. Target URLs, request bodies, and raw client IPs are not logged. Error logs use exception classes rather than messages that may contain submitted values. Health exposes status only; readiness includes the database. Graceful shutdown is enabled.
