package com.varun.shortener.support;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.varun.shortener.analytics.AnalyticsService;
import com.varun.shortener.repository.*;
import com.varun.shortener.service.*;
import com.varun.shortener.web.InMemoryRateLimiter;
import java.time.*;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.*;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.*;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.PostgreSQLContainer;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(PostgresIntegrationTest.TimeConfiguration.class)
public abstract class PostgresIntegrationTest {
    public static final Instant NOW = Instant.parse("2026-01-01T12:00:00Z");
    // JVM-wide container avoids cached Spring contexts pointing at a stopped per-class container.
    // Deliberately no disabledWithoutDocker: missing Docker is a failed acceptance check.
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16-alpine");
    static { POSTGRES.start(); }

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry properties) {
        properties.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        properties.add("spring.datasource.username", POSTGRES::getUsername);
        properties.add("spring.datasource.password", POSTGRES::getPassword);
    }

    @TestConfiguration
    public static class TimeConfiguration {
        @Bean @Primary MutableClock testClock() { return new MutableClock(NOW); }
    }

    @Autowired protected MockMvc mvc;
    @Autowired protected ObjectMapper json;
    @Autowired protected UrlService urls;
    @Autowired protected RedirectService redirects;
    @Autowired protected AnalyticsService analytics;
    @Autowired protected UrlRepository urlRepository;
    @Autowired protected ClickEventRepository clickRepository;
    @Autowired protected MutableClock clock;
    @Autowired protected JdbcTemplate jdbc;
    @Autowired InMemoryRateLimiter limiter;

    @BeforeEach
    void resetFixture() {
        // Only the disposable Testcontainers database is touched.
        jdbc.update("DELETE FROM click_events");
        jdbc.update("DELETE FROM urls");
        clock.set(NOW.plus(Duration.ofDays(365)));
        limiter.cleanup();
        clock.set(NOW);
    }
}
