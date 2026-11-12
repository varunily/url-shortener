# URL Shortener — Phase 1 backend

Java 21, Spring Boot 3.5.4, PostgreSQL 16, Flyway, Spring Data JPA, Validation, Actuator, OpenAPI, and Maven. Package: com.varun.shortener. Application port: 8080.

Five endpoints support creation, HTTP 302 redirects, metadata, click statistics, and idempotent disabling. Codes contain seven case-sensitive Base62 characters.

## Quick start with Docker

Prerequisite: running Docker Desktop or Docker Engine with Compose.

~~~bash
docker compose up -d
docker compose ps
curl --fail http://localhost:8080/actuator/health/readiness
bash scripts/smoke-test.sh
~~~

The first command builds the application on a clean checkout. Wait for both containers to be healthy before running the smoke script. After editing application code, rebuild with:

~~~bash
docker compose up -d --build
~~~

- Application: http://localhost:8080
- Swagger UI: http://localhost:8080/swagger-ui/index.html
- OpenAPI JSON: http://localhost:8080/v3/api-docs
- PostgreSQL from the host: localhost:5433, database shortener
- PostgreSQL inside Compose: db:5432

Port 5433 avoids this workstation's existing PostgreSQL server on 5432. DB_PORT changes the host database port.

Compose defaults to development-only credentials: user **shortener**, password **local-development-only**. Published ports bind to loopback. Optional local overrides:

~~~bash
cp .env.example .env
# Edit .env before starting Compose.
~~~

Changing credentials after the persistent database volume is initialized does not update the existing database user's password. To stop these local services while retaining data:

~~~bash
docker compose stop
~~~

## Run with a host JVM

Prerequisites: JDK **21**, Maven 3.9+ (or the wrapper), and running Docker.

On macOS, select an installed Java 21 runtime:

~~~bash
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export PATH="$JAVA_HOME/bin:$PATH"
java -version
mvn -version
~~~

Maven Enforcer requires Java 21. An active Java 25 installation must be switched. The temporary JDK downloaded for validation on this workstation is documented in [test results](docs/testing.md).

~~~bash
docker compose up -d db
export DATABASE_URL='jdbc:postgresql://localhost:5433/shortener'
export DB_USER='shortener'
export DB_PASSWORD='local-development-only'
export BASE_URL='http://localhost:8080'
./mvnw spring-boot:run
~~~

If the Compose application is using 8080, stop only that project service first with:

~~~bash
docker compose stop app
~~~

A host JVM does not automatically load .env; export the variables as above.

## Build and test

~~~bash
mvn clean verify

# Equivalent pinned Maven distribution:
./mvnw clean verify

# Unit and HTTP slice tests only; NOT full acceptance:
./mvnw test
~~~

Surefire runs unit tests; Failsafe runs integration tests during verify. Integration tests start a real disposable PostgreSQL 16 container and apply both migrations. Missing Docker fails the build; tests are never silently skipped.

The Dockerfile packages with tests disabled because its build stage has no Docker daemon for Testcontainers. Image construction is not a substitute for full host verification.

See [test execution and results](docs/testing.md). Reports appear in target/surefire-reports and target/failsafe-reports.

## API

| Method | Path | Success |
|---|---|---|
| POST | /api/v1/urls | 201, URL metadata |
| GET | /{code} | 302, original URL in Location |
| GET | /api/v1/urls/{code} | 200, URL metadata |
| GET | /api/v1/urls/{code}/stats | 200, lifetime and UTC daily statistics |
| PATCH | /api/v1/urls/{code}/disable | 200, disabled metadata |

~~~bash
curl -i -X POST http://localhost:8080/api/v1/urls \
  -H 'Content-Type: application/json' \
  -d '{"originalUrl":"https://example.com/articles?id=42"}'
~~~

Illustrative response:

~~~json
{
  "shortCode": "abc1234",
  "shortUrl": "http://localhost:8080/abc1234",
  "originalUrl": "https://example.com/articles?id=42",
  "createdAt": "2026-11-11T23:00:00Z",
  "expiresAt": null,
  "status": "ACTIVE"
}
~~~

Use the actual returned code. [API examples](docs/api-examples.md) include the full curl flow and error contracts. The smoke script extracts the generated code and asserts each step.

## Configuration

| Variable | Default / requirement |
|---|---|
| DATABASE_URL | JDBC URL; host JVM defaults to jdbc:postgresql://localhost:5433/shortener; Compose defaults to jdbc:postgresql://db:5432/shortener |
| DB_USER | shortener |
| DB_PASSWORD | Required for host JVM; development-only fallback in Compose |
| BASE_URL | http://localhost:8080; HTTP(S) origin without credentials, path, query, or fragment |
| DB_PORT | Compose host database port; 5433 |

BASE_URL controls returned links, not the listen port. Plain postgres:// URLs are not JDBC URLs. Production credentials must come from the deployment environment or a secret manager.

## Behavior

- Absolute HTTP/HTTPS destinations, up to 2,048 characters. Credentials, control characters, malformed hosts, and invalid ports are rejected.
- Internationalized hostnames must use punycode. Destinations are not fetched or DNS-resolved. Private/local addresses are allowed; reputation is not checked.
- Optional expiresAt is an ISO-8601 instant with an offset and must be in the future. Creation/expiration use PostgreSQL microsecond precision and UTC output.
- Unknown/malformed codes: 404. Expired/disabled redirects: 410. Metadata and stats remain available. HEAD on a short URL: 405 without a click.
- Collisions allow an initial attempt plus **five retries**. Other database failures are not treated as collisions.
- Creation admits 100 POST attempts per connection IP per rolling hour. Invalid bodies count; rate-limit rejections do not extend the window. Forwarded headers are ignored.
- Each accepted GET records one durable event before 302. Failed analytics writes prevent redirect. Bots/repeated requests count; events do not prove destination loading.
- No authentication: anyone knowing a code can inspect or disable it. Codes are identifiers, not authorization.
- Rate limits are per JVM, reset on restart, and bounded to 10,000 active IP entries. Capacity exhaustion returns 503.

## Architecture and future work

- [Architecture and diagrams](docs/architecture.md)
- [Decisions, reliability, security, and scalability](docs/design-decisions.md)
- [Phase 2 orchestration contract and demonstrations](docs/phase-2-orchestration.md)

This is the backend only. The Python/LangGraph engine, persistent workflow state, scheduler, approvals, audit store, and workflow metrics remain Phase 2 work.

The original src/Main.java is preserved outside Maven's source roots. Open pom.xml as a Maven project in IntelliJ and select JDK 21. Generated artifacts, IDE files, and local secrets are ignored by Git.
