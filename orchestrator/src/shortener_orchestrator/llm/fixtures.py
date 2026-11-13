"""Deterministic offline Java fixtures, explicitly not LLM-generated code."""
from ..tools.repository import git

JAVA = "src/main/java/com/varun/shortener/"
TEST = "src/test/java/com/varun/shortener/"
MIGRATIONS = "src/main/resources/db/migration/"

def original(context, path):
    from pathlib import Path
    return git(Path(context["workspace"]), "show", context["baseline"] + ":" + path)

def replacement(text, before, after):
    if before not in text:
        raise ValueError("FakeLLM fixture is incompatible with this baseline")
    return text.replace(before, after)

def aliases(context):
    changes = {}
    changes[MIGRATIONS + "V3__custom_aliases.sql"] = """ALTER TABLE urls ALTER COLUMN short_code TYPE VARCHAR(32);
ALTER TABLE urls DROP CONSTRAINT ck_urls_short_code;
ALTER TABLE urls ADD CONSTRAINT ck_urls_short_code CHECK (short_code ~ '^[A-Za-z0-9]{3,32}$');
"""
    changes[JAVA + "entity/ShortUrl.java"] = replacement(original(context, JAVA + "entity/ShortUrl.java"),
                                                       "length = 7", "length = 32")
    changes[JAVA + "dto/CreateUrlRequest.java"] = """package com.varun.shortener.dto;

import com.varun.shortener.validation.HttpUrl;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import jakarta.validation.constraints.Pattern;
import java.time.Instant;

public record CreateUrlRequest(
        @NotBlank @Size(max = 2048) @HttpUrl String originalUrl,
        Instant expiresAt,
        @Pattern(regexp = "[A-Za-z0-9]{3,32}", message = "must contain 3 to 32 Base62 characters") String customAlias) {
    public CreateUrlRequest(String originalUrl, Instant expiresAt) {
        this(originalUrl, expiresAt, null);
    }
}
"""
    service = original(context, JAVA + "service/UrlService.java")
    service = replacement(service, 'private static final int MAX_COLLISION_RETRIES = 5;',
        'private static final int MAX_COLLISION_RETRIES = 5;\n'
        '    private static final java.util.Set<String> RESERVED = java.util.Set.of("api", "actuator", "swagger", "error");')
    service = replacement(service, "        for (int attempt = 0;", """        if (request.customAlias() != null) {
            String alias = request.customAlias();
            if (!alias.matches("[A-Za-z0-9]{3,32}") || RESERVED.contains(alias.toLowerCase(java.util.Locale.ROOT))) {
                throw new ApiException(ErrorCode.INVALID_REQUEST);
            }
            if (urls.insertIfAvailable(alias, request.originalUrl(), now, expires) != 1) {
                throw new ApiException(ErrorCode.ALIAS_CONFLICT);
            }
            return mapper.toResponse(urls.findByShortCode(alias).orElseThrow(), now);
        }
        for (int attempt = 0;""")
    changes[JAVA + "service/UrlService.java"] = replacement(service, '"[A-Za-z0-9]{7}"', '"[A-Za-z0-9]{3,32}"')
    changes[JAVA + "exception/ErrorCode.java"] = replacement(
        original(context, JAVA + "exception/ErrorCode.java"), "    INVALID_REQUEST(",
        '    ALIAS_CONFLICT(HttpStatus.CONFLICT, "The requested alias is already in use."),\n    INVALID_REQUEST(')
    changes[TEST + "integration/CustomAliasesIT.java"] = """package com.varun.shortener.integration;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.varun.shortener.dto.CreateUrlRequest;
import com.varun.shortener.support.PostgresIntegrationTest;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

class CustomAliasesIT extends PostgresIntegrationTest {
    @Test
    void customAliasSupportsTheCompleteLifecycle() throws Exception {
        mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON)
                .content("{\\"originalUrl\\":\\"https://example.com\\",\\"customAlias\\":\\"MyDocs2026\\"}"))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.shortCode").value("MyDocs2026"));
        mvc.perform(get("/MyDocs2026")).andExpect(status().isFound())
                .andExpect(header().string("Location", "https://example.com"));
        mvc.perform(get("/api/v1/urls/MyDocs2026/stats")).andExpect(status().isOk())
                .andExpect(jsonPath("$.totalClicks").value(1));
        mvc.perform(patch("/api/v1/urls/MyDocs2026/disable")).andExpect(status().isOk());
        mvc.perform(get("/MyDocs2026")).andExpect(status().isGone());
    }

    @Test
    void collisionReturns409AndNeverOverwrites() throws Exception {
        urls.create(new CreateUrlRequest("https://first.example", null, "shared"));
        mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON)
                .content("{\\"originalUrl\\":\\"https://second.example\\",\\"customAlias\\":\\"shared\\"}"))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("ALIAS_CONFLICT"));
        assertThat(urls.get("shared").originalUrl()).isEqualTo("https://first.example");
    }

    @Test
    void rejectsInvalidAndReservedAliases() throws Exception {
        for (String alias : new String[]{"ab", "a".repeat(33), "has-dash", "api", "error", "Actuator"}) {
            mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON)
                    .content(json.writeValueAsString(new CreateUrlRequest("https://example.com", null, alias))))
                    .andExpect(status().isBadRequest());
        }
        assertThat(urlRepository.count()).isZero();
    }

    @Test
    void aliasesAreCaseSensitiveAndGeneratedCodesRemainSevenCharacters() {
        urls.create(new CreateUrlRequest("https://one.example", null, "Abc"));
        urls.create(new CreateUrlRequest("https://two.example", null, "abc"));
        assertThat(urls.get("Abc").originalUrl()).isNotEqualTo(urls.get("abc").originalUrl());
        assertThat(urls.create(new CreateUrlRequest("https://example.com", null)).shortCode())
                .matches("[A-Za-z0-9]{7}");
        assertThat(urls.create(new CreateUrlRequest("https://example.com", null, "a".repeat(32))).shortCode()).hasSize(32);
    }

    @Test
    void concurrentCreatorsCannotClaimTheSameAlias() throws Exception {
        try (var executor = Executors.newFixedThreadPool(2)) {
            var start = new CountDownLatch(1);
            Callable<Boolean> job = () -> {
                start.await();
                try { urls.create(new CreateUrlRequest("https://example.com", null, "raceAlias")); return true; }
                catch (com.varun.shortener.exception.ApiException ex) {
                    assertThat(ex.code()).isEqualTo(com.varun.shortener.exception.ErrorCode.ALIAS_CONFLICT);
                    return false;
                }
            };
            var first = executor.submit(job);
            var second = executor.submit(job);
            start.countDown();
            assertThat(java.util.List.of(first.get(10, TimeUnit.SECONDS), second.get(10, TimeUnit.SECONDS)))
                    .containsExactlyInAnyOrder(true, false);
        }
        assertThat(urlRepository.count()).isEqualTo(1);
    }
}
"""
    changes["docs/custom-aliases.md"] = """# Custom aliases
POST /api/v1/urls accepts optional customAlias with 3–32 case-sensitive Base62 characters.
Reserved names api, actuator, swagger, and error are rejected case-insensitively.
A claimed alias returns 409 ALIAS_CONFLICT. Generated codes remain seven characters.
Aliases support existing redirect, metadata, stats, and disable endpoints.
V3 widens the code column and check constraint. V1/V2 remain unchanged.
"""
    return changes

def expiration(context):
    changes = {}
    changes[MIGRATIONS + "V3__archive_expired_urls.sql"] = """ALTER TABLE urls ADD COLUMN archived_at TIMESTAMPTZ;
ALTER TABLE urls ADD CONSTRAINT ck_urls_archival
    CHECK (archived_at IS NULL OR (expires_at IS NOT NULL AND archived_at >= expires_at));
CREATE INDEX ix_urls_pending_expiration ON urls (expires_at, id)
    WHERE archived_at IS NULL AND expires_at IS NOT NULL;
"""
    entity = original(context, JAVA + "entity/ShortUrl.java")
    entity = replacement(entity, "    private boolean disabled;",
                         '    private boolean disabled;\n    @Column(name = "archived_at")\n    private Instant archivedAt;')
    changes[JAVA + "entity/ShortUrl.java"] = replacement(entity, "    public Long getId()",
                         "    public Instant getArchivedAt() { return archivedAt; }\n    public Long getId()")
    changes[JAVA + "service/ExpirationArchiveService.java"] = '''package com.varun.shortener.service;

import java.sql.Timestamp;
import java.time.Clock;
import java.time.temporal.ChronoUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ExpirationArchiveService {
    private final JdbcTemplate jdbc;
    private final Clock clock;
    private final int batchSize;

    public ExpirationArchiveService(JdbcTemplate jdbc, Clock clock,
            @Value("${shortener.cleanup.batch-size:100}") int batchSize) {
        if (batchSize < 1 || batchSize > 1000) throw new IllegalArgumentException("Invalid cleanup batch size");
        this.jdbc = jdbc; this.clock = clock; this.batchSize = batchSize;
    }

    @Transactional(timeout = 5)
    public int archiveBatch() {
        var now = Timestamp.from(clock.instant().truncatedTo(ChronoUnit.MICROS));
        return jdbc.update("""
                WITH candidates AS (
                    SELECT id FROM urls
                    WHERE expires_at <= ? AND archived_at IS NULL
                    ORDER BY expires_at, id LIMIT ? FOR UPDATE SKIP LOCKED
                )
                UPDATE urls SET archived_at = ? FROM candidates WHERE urls.id = candidates.id
                """, now, batchSize, now);
    }
}
'''
    changes[JAVA + "service/ExpirationCleanupScheduler.java"] = '''package com.varun.shortener.service;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ExpirationCleanupScheduler {
    private final ExpirationArchiveService archive;
    public ExpirationCleanupScheduler(ExpirationArchiveService archive) { this.archive = archive; }

    @Scheduled(fixedDelayString = "${shortener.cleanup.delay-ms:60000}",
               initialDelayString = "${shortener.cleanup.initial-delay-ms:60000}")
    public void cleanup() { archive.archiveBatch(); }
}
'''
    changes[TEST + "integration/ExpirationArchiveIT.java"] = """package com.varun.shortener.integration;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.varun.shortener.dto.CreateUrlRequest;
import com.varun.shortener.service.*;
import com.varun.shortener.support.PostgresIntegrationTest;
import java.time.Duration;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

class ExpirationArchiveIT extends PostgresIntegrationTest {
    @Autowired ExpirationArchiveService archive;
    @Autowired ExpirationCleanupScheduler scheduler;

    @Test
    void cleanupPreserves410MappingAndClickStatistics() throws Exception {
        var expired = urls.create(new CreateUrlRequest("https://example.com", NOW.plusSeconds(1)));
        redirects.redirect(expired.shortCode());
        var active = urls.create(new CreateUrlRequest("https://active.example", null));
        clock.advance(Duration.ofSeconds(1));
        scheduler.cleanup();
        var stored = urlRepository.findByShortCode(expired.shortCode()).orElseThrow();
        assertThat(stored.getArchivedAt()).isEqualTo(clock.instant());
        assertThat(stored.getOriginalUrl()).isEqualTo(expired.originalUrl());
        assertThat(urlRepository.findByShortCode(active.shortCode()).orElseThrow().getArchivedAt()).isNull();
        mvc.perform(get("/" + expired.shortCode())).andExpect(status().isGone())
                .andExpect(jsonPath("$.code").value("URL_EXPIRED"));
        assertThat(analytics.stats(expired.shortCode()).totalClicks()).isEqualTo(1);
        assertThat(urlRepository.count()).isEqualTo(2);
        assertThat(archive.archiveBatch()).isZero();
    }

    @Test
    void skipsFutureAndPermanentLinksAndPreservesDisabledPrecedence() throws Exception {
        var disabled = urls.create(new CreateUrlRequest("https://example.com", NOW.plusSeconds(1)));
        urls.disable(disabled.shortCode());
        urls.create(new CreateUrlRequest("https://example.com", NOW.plusSeconds(300)));
        urls.create(new CreateUrlRequest("https://example.com", null));
        clock.advance(Duration.ofSeconds(1));
        assertThat(archive.archiveBatch()).isEqualTo(1);
        mvc.perform(get("/" + disabled.shortCode())).andExpect(status().isGone())
                .andExpect(jsonPath("$.code").value("URL_DISABLED"));
        assertThat(clickRepository.count()).isZero();
    }

    @Test
    void batchesAreBoundedAndConcurrentWorkersDoNotDoubleArchive() throws Exception {
        for (int i = 0; i < 105; i++) urls.create(new CreateUrlRequest("https://example.com", NOW.plusSeconds(1)));
        clock.advance(Duration.ofSeconds(1));
        assertThat(archive.archiveBatch()).isEqualTo(100);
        try (var executor = Executors.newFixedThreadPool(2)) {
            var first = executor.submit(archive::archiveBatch);
            var second = executor.submit(archive::archiveBatch);
            assertThat(first.get(10, TimeUnit.SECONDS) + second.get(10, TimeUnit.SECONDS)).isEqualTo(5);
        }
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM urls WHERE archived_at IS NOT NULL", Long.class)).isEqualTo(105);
        assertThat(urlRepository.count()).isEqualTo(105);
    }
}
"""
    changes["docs/expiration-archive.md"] = """# Expiration archival
A scheduled worker marks expired rows with archived_at; it never deletes mappings or click events.
Expired redirects retain 410 / URL_EXPIRED. Disabled state still takes precedence.
Metadata and lifetime statistics remain available. V3 adds the marker and partial expiration index.
The default interval and initial delay are 60 seconds, with at most 100 rows per invocation.
Configure shortener.cleanup.delay-ms, shortener.cleanup.initial-delay-ms, and shortener.cleanup.batch-size.
A transactional FOR UPDATE SKIP LOCKED batch permits multiple workers without double archival.
Archival is lifecycle bookkeeping; it does not reduce retained storage.
"""
    return changes

def clarified_security(context):
    changes = expiration(context)
    days = int(context["clarification"]["max_expiration_days"])
    changes[JAVA + "service/UrlService.java"] = replacement(original(context, JAVA + "service/UrlService.java"),
        "        for (int attempt = 0;", f"""        if (expires != null && expires.isAfter(now.plus(java.time.Duration.ofDays({days})))) {{
            throw new ApiException(ErrorCode.INVALID_REQUEST);
        }}
        for (int attempt = 0;""")
    changes[TEST + "integration/ClarifiedSecurityIT.java"] = f"""package com.varun.shortener.integration;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.varun.shortener.dto.CreateUrlRequest;
import com.varun.shortener.support.PostgresIntegrationTest;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

class ClarifiedSecurityIT extends PostgresIntegrationTest {{
    @Test
    void rejectsExpiryBeyondApprovedMaximumAndAcceptsBoundary() throws Exception {{
        var rejected = new CreateUrlRequest("https://example.com", NOW.plus(Duration.ofDays({days})).plusSeconds(1));
        mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(rejected)))
                .andExpect(status().isBadRequest());
        var accepted = new CreateUrlRequest("https://example.com", NOW.plus(Duration.ofDays({days})));
        mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(accepted)))
                .andExpect(status().isCreated());
    }}

    @Test
    void preservesHttpHttpsAndBlocksCredentialsAndHeaderInjection() throws Exception {{
        for (String original : new String[]{{"http://example.com", "https://example.com"}}) {{
            mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON)
                    .content(json.writeValueAsString(new CreateUrlRequest(original, null))))
                    .andExpect(status().isCreated());
        }}
        for (String original : new String[]{{"https://user:pass@example.com", "https://example.com/%0d%0aInjected:1"}}) {{
            mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON)
                    .content(json.writeValueAsString(new CreateUrlRequest(original, null))))
                    .andExpect(status().isBadRequest());
        }}
        assertThat(urlRepository.count()).isEqualTo(2);
    }}
}}
"""
    changes["docs/clarified-security.md"] = f"""# Human-clarified security and expiration
HTTP and HTTPS remain supported. Credentials and control characters remain rejected.
Explicit expiration is limited to {days} days; omitted expiration still means no expiry.
Expired mappings and click statistics are preserved by archival.
This bounded demo policy does not perform destination reputation or SSRF filtering.
"""
    return changes

def all_changes(context):
    scenario = context["scenario"]
    changes = aliases(context) if scenario == "greenfield" else (
        clarified_security(context) if scenario == "ambiguous" else expiration(context))
    if context.get("fault"):
        fail = context["fault"] == "always" or context.get("retry_count", 0) == 0
        changes[TEST + "service/InjectedFailureTest.java"] = f"""package com.varun.shortener.service;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class InjectedFailureTest {{
    @Test void controlledFailure() {{
        // Explicit failure-injection demonstration, revision {context.get("revision", 1)}.
        assertTrue({str(not fail).lower()}, "Deliberate workflow recovery demonstration");
    }}
}}
"""
    migration_test = TEST + "integration/PersistenceAndMigrationIT.java"
    changes[migration_test] = replacement(original(context, migration_test),
        '.containsExactly("1", "2");', '.containsExactly("1", "2", "3");')
    return changes

def tasks(context):
    paths = list(all_changes(context))
    if context.get("retry_count", 0):
        chosen = [TEST + "service/InjectedFailureTest.java"] if context.get("fault") else paths
        return [{"id": "repair", "description": "Repair from actual failure evidence", "depends_on": [], "files": chosen}]
    schema = [p for p in paths if "/db/migration/" in p or "/entity/" in p]
    implementation = [p for p in paths if p.startswith(JAVA) and p not in schema]
    regression = [p for p in paths if p not in schema + implementation]
    return [
        {"id": "schema", "description": "Add forward-only migration and persistence mapping", "depends_on": [], "files": schema},
        {"id": "implementation", "description": "Implement agreed behavior", "depends_on": ["schema"], "files": implementation},
        {"id": "regression", "description": "Add regressions and feature documentation", "depends_on": ["implementation"], "files": regression},
    ]
