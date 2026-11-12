package com.varun.shortener.integration;

import static org.assertj.core.api.Assertions.*;
import com.varun.shortener.dto.CreateUrlRequest;
import com.varun.shortener.support.PostgresIntegrationTest;
import java.sql.Timestamp;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;

class PersistenceAndMigrationIT extends PostgresIntegrationTest {
    @Test
    void appliesBothMigrationsAndPersistsAcrossTransactions() {
        assertThat(jdbc.queryForList("SELECT version FROM flyway_schema_history WHERE success ORDER BY installed_rank",
                String.class)).containsExactly("1", "2");
        var link = urls.create(new CreateUrlRequest("https://example.com/a?x=1", NOW.plusSeconds(60)));
        var loaded = urls.get(link.shortCode());
        assertThat(loaded).isEqualTo(link);
        assertThat(jdbc.queryForObject("SELECT original_url FROM urls WHERE short_code = ?", String.class,
                link.shortCode())).isEqualTo(link.originalUrl());
        redirects.redirect(link.shortCode());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM click_events", Long.class)).isEqualTo(1);
    }

    @Test
    void databaseEnforcesCodeUniquenessAndAlphabet() {
        String sql = "INSERT INTO urls(short_code, original_url, created_at) VALUES (?, ?, ?)";
        jdbc.update(sql, "abc1234", "https://example.com", Timestamp.from(NOW));
        assertThatThrownBy(() -> jdbc.update(sql, "abc1234", "https://other.example", Timestamp.from(NOW)))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> jdbc.update(sql, "bad!!!!", "https://example.com", Timestamp.from(NOW)))
                .isInstanceOf(DataIntegrityViolationException.class);
        jdbc.update(sql, "Abc1234", "https://example.com", Timestamp.from(NOW));
        assertThat(urlRepository.count()).isEqualTo(2); // Case-sensitive Base62.
    }

    @Test
    void databaseEnforcesForeignKeyAndExpiration() {
        assertThatThrownBy(() -> jdbc.update("INSERT INTO click_events(url_id, accessed_at) VALUES (-1, ?)", Timestamp.from(NOW)))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> jdbc.update(
                "INSERT INTO urls(short_code, original_url, created_at, expires_at) VALUES (?, ?, ?, ?)",
                "abc1234", "https://example.com", Timestamp.from(NOW), Timestamp.from(NOW)))
                .isInstanceOf(DataIntegrityViolationException.class);
    }
}
