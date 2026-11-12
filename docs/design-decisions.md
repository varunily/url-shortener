# Design decisions and trade-offs

## Stack and boundaries

Java 21, Spring Boot 3.5.4, PostgreSQL 16, and application port 8080 follow the assignment. Springdoc 2.8.9 and Testcontainers 1.21.4 are pinned; the latter supports this workstation's Docker 29 minimum API. The Spring Boot BOM manages remaining versions.

Pins improve reproducibility but do not establish vulnerability-free dependencies. Production release needs dependency/security review and an approved upgrade policy. There is no authentication, Redis, Kafka, or microservice layer.

## Codes

Seven Base62 characters provide 62^7 = 3,521,614,606,208 candidates. SecureRandom chooses characters uniformly. Randomness reduces collision probability; the database unique constraint guarantees uniqueness.

The approved retry policy is one initial attempt plus five retries. A targeted conflict clause handles only code collisions. There is no pre-check race or broad integrity-error retry. PostgreSQL-specific SQL trades portability for explicit concurrent semantics. Repeated original URLs receive independent mappings; no idempotency-key contract exists.

Reference: [PostgreSQL INSERT / ON CONFLICT](https://www.postgresql.org/docs/16/sql-insert.html).

## Analytics and reliability

Append-only events are the source of truth. Totals, last access, and UTC daily counts derive from those events, avoiding lost read-modify-write counter updates. No raw visitor metadata is collected.

Costs: one synchronous database write per redirect, indefinite storage growth, and aggregation work proportional to a link's events. Retention, partitioning, pre-aggregation, asynchronous delivery, and caching are future changes requiring impact analysis and regression tests.

Shared row locks permit concurrent redirects to the same link; disable uses an exclusive lock. Very hot links can delay disable. Five-second transaction timeouts, three-second connection acquisition timeout, and a bounded connection pool constrain resource consumption. Database unavailability also makes redirects unavailable because durable analytics are required.

REPEATABLE READ keeps stats queries consistent. Events committed after the snapshot begins are naturally excluded. Events count accepted redirect requests, including bots/repeated visits, not unique visitors or completed destination loads. A client disconnect after database commit can still leave an event.

Reference: [PostgreSQL transaction isolation](https://www.postgresql.org/docs/16/transaction-iso.html).

## Time and lifecycle

An injectable Clock enables deterministic boundary tests. Timestamps are stored as timestamptz and returned in UTC. Creation and expiration are truncated to microseconds before validation/insertion to avoid PostgreSQL rounding reversing an inequality.

No re-enable, editing, custom aliases, listing, ownership, or deletion API is included. Disable is idempotent and permanent in this phase. HEAD returns 405 and does not count.

Daily stats cover the lifetime of the link, list only dates with clicks, and sort ascending. Empty results return zero, null last-access, and an empty list. High-volume lifetime statistics can become expensive; date filtering/pagination is future work.

## Input and abuse

Only absolute HTTP(S) destinations with parseable hosts are accepted. Credentials, malformed ports, literal/encoded control characters, and more than 2,048 characters are rejected. Internationalized hosts require punycode. The target path/query is preserved.

The server never fetches or resolves targets. It therefore does not issue server-side requests to submitted destinations. Local/private targets are permitted. This is not a malware scanner, destination allowlist, or phishing detector. Public operation needs an abuse/ownership policy.

No authentication means any caller knowing a code can inspect, read stats, or disable it. Codes are not authorization. Arbitrary cross-origin browser access is not enabled. TLS, public exposure, production infrastructure, secret rotation, and backups remain deployment responsibilities.

## Rate limiting

A synchronized rolling timestamp log admits at most 100 creation attempts per remote IP in the preceding hour. Each queue holds at most 100 entries, and at most 10,000 active IP entries are retained. Scheduled cleanup removes idle entries. Active entries are never evicted to admit new clients; capacity exhaustion returns 503.

Invalid JSON and validation failures still consume quota. Rate-limit rejections do not append timestamps. Alternate encoded/matrix-parameter representations of the endpoint consume the same quota. Forwarded headers are ignored to prevent client spoofing.

This simple global lock is appropriate for modest volume but limits scaling. Quotas reset on restart and apply per JVM. NAT users share quota. Behind a proxy, callers share the proxy's quota until an approved trusted-proxy policy is implemented.

## Operations and privacy

Environment variables supply secrets. Compose credentials are local demonstration defaults. Loopback port bindings and a non-root JVM limit local exposure; a persistent volume retains data.

Logs use generated request IDs and route templates. SQL exception logging is suppressed because constraint messages can echo sensitive input. API failure logs contain exception class names. This reduces diagnostic detail deliberately; deeper debugging requires controlled access and redaction.

Database/transaction failures return sanitized 503 responses. Unexpected failures return 500. There are no automatic write retries after uncertain commit outcomes. A client retry after a lost POST response can create another mapping.

Readiness includes the database. Single application/database instances remain failure domains. Backups, failover, sustained load tests, dependency scans, and production deployment checks are not established by functional tests.

## Evidence limits

Concurrent tests exercise modest local workloads, not a production load envelope. Docker image packaging skips tests and must be paired with full host verification. [Testing results](testing.md) record what actually executed.
