# Test execution and recorded results

## Final executed result — 2026-11-11

The final full build finished at 18:29:26 America/New_York (23:29:26 UTC). These are executed results, not predictions.

| Check | Result |
|---|---|
| Maven clean verify | PASS, exit 0 |
| Surefire unit / HTTP slice tests | 59 tests, 0 failures, 0 errors, 0 skipped |
| Failsafe PostgreSQL integration tests | 16 tests, 0 failures, 0 errors, 0 skipped |
| Testcontainers | Ran successfully against a real PostgreSQL 16 container |
| Docker Compose configuration | PASS |
| Docker image build and local start | PASS |
| Exact docker compose up -d command on final configuration | PASS |
| Application and database health | Both healthy |
| curl create → redirect → stats → disable | PASS |
| Smoke script shell syntax | PASS |
| Maven wrapper startup | PASS; Maven 3.9.12 on Java 21.0.13 |

The smoke flow created code **8fm32QL**, received 302 with the expected Location, observed exactly one click, disabled the mapping, received 410, and confirmed the count stayed at one. This is local demonstration data, not a fixed fixture or a code to hard-code into examples.

## Environment and exact commands used

- macOS arm64
- Eclipse Temurin Java 21.0.13, downloaded into a temporary directory
- Maven 3.9.12
- Spring Boot 3.5.4
- Testcontainers 1.21.4
- Docker Engine 29.2.0 / Docker Desktop 4.60.1
- Docker Compose 5.0.2
- PostgreSQL image: postgres:16-alpine

The workstation's default Java is 25. The build was explicitly run with Java 21:

~~~bash
export JAVA_HOME='/private/tmp/jdk-21.0.13+9/Contents/Home'
export PATH="$JAVA_HOME/bin:$PATH"
mvn -B -ntp clean verify

docker compose config --quiet
docker compose up -d --build
docker compose up -d
docker compose ps
bash scripts/smoke-test.sh
~~~

The temporary JDK path is specific to this workstation and may be removed by OS cleanup. For a durable setup, install/select JDK 21 and set JAVA_HOME to that installation. Docker builds use Java 21 independently of the host JDK.

The first Compose start encountered the existing host PostgreSQL server on 5432. The final configuration publishes the project database on 5433, and the rerun succeeded. No existing database service was stopped.

The first compilation exposed a Spring constructor signature mismatch, which was fixed. A later added rollback test initially used an invalid Mockito real-method call on a repository proxy; the injection was corrected to execute a real JDBC insert in the service transaction before raising the simulated failure. The final verification includes those fixes.

## Coverage map

| Test class | Checks |
|---|---|
| HttpUrlValidatorTest | Schemes, hosts, credentials, malformed URLs, controls, ports, length |
| ShortenerPropertiesTest | Invalid public-origin configuration |
| SecureRandomShortCodeGeneratorTest | Seven Base62 characters and output variety |
| UrlServiceTest | Mapping, collision retry count, database errors, expiration, disable |
| RedirectServiceTest | Recording, expiration boundary, disabled and missing links |
| AnalyticsServiceTest | Zero-click response |
| ApiContractTest | Exact create response, validation, errors, 302 headers, HEAD behavior |
| InMemoryRateLimiterTest | Rolling window, independent IPs, 500 parallel attempts, capacity cleanup |
| CreationRateLimitFilterTest | Encoded, duplicate-slash, and matrix-parameter paths consume quota |
| UrlLifecycleIT | Full API flow, expiry, UTC daily aggregation, health and OpenAPI |
| PersistenceAndMigrationIT | Both Flyway migrations, committed persistence, DB constraints |
| CollisionHandlingIT | Five retries then success, exhaustion, simultaneous same-code candidates |
| ConcurrentRequestsIT | 100 redirects, 50 creators, redirect/disable race |
| RateLimitIT | 100-request API quota, forwarded-header spoofing, non-POST routes, renewal |
| AnalyticsFailureIT | Rollback after a real event insert, 503 without redirect, recovery |

Mockito isolates dependencies in unit tests. Integration tests use the actual Spring transaction proxies, JPA repositories, Flyway migrations, and PostgreSQL. The rollback test injects a failure after a real SQL insert to verify transaction atomicity; it does not claim to simulate a network outage.

## Reproduce

With Java 21 and a running Docker daemon:

~~~bash
mvn clean verify
# Or use the included Maven wrapper:
./mvnw clean verify
~~~

Unit/HTTP slice tests only:

~~~bash
mvn test
~~~

A focused integration test, while diagnosing a failure:

~~~bash
mvn -Dtest=UrlServiceTest -Dit.test=CollisionHandlingIT verify
~~~

Reports:
- target/surefire-reports/TEST-*.xml
- target/failsafe-reports/TEST-*.xml
- target/failsafe-reports/failsafe-summary.xml

JUnit test cases are not configured to silently skip when Docker is missing. The integration container is shared across test classes within one JVM, preventing cached Spring contexts from pointing at stopped containers. Fixture cleanup affects only the disposable Testcontainers database. Ryuk reclaims its containers when the test JVM exits.

The Dockerfile deliberately skips tests during packaging; Docker build success is not a full test result.

## Limits

No production deployment, external load test, penetration test, dependency vulnerability scan, backup/restore drill, multi-instance validation, or Python orchestration engine execution was performed. Concurrent tests cover bounded local workloads. Phase 2 capabilities are design documentation only.

The application and its PostgreSQL container were left running locally for demonstration. No commits, pushes, or deployments were performed.
