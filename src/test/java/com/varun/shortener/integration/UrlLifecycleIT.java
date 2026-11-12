package com.varun.shortener.integration;

import static org.assertj.core.api.Assertions.*;
import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.varun.shortener.dto.*;
import com.varun.shortener.entity.UrlStatus;
import com.varun.shortener.support.PostgresIntegrationTest;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

class UrlLifecycleIT extends PostgresIntegrationTest {
    @Test
    void createRedirectStatsDisableFlow() throws Exception {
        var created = mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON)
                .content("{\"originalUrl\":\"https://example.com/path?q=1\"}"))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.shortCode", matchesPattern("[A-Za-z0-9]{7}")))
                .andReturn().getResponse();
        var result = json.readValue(created.getContentAsString(), UrlResponse.class);
        String code = result.shortCode();
        assertThat(result.createdAt()).isEqualTo(NOW);
        mvc.perform(get("/api/v1/urls/" + code)).andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ACTIVE"));
        mvc.perform(get("/api/v1/urls/" + code + "/stats")).andExpect(status().isOk())
                .andExpect(jsonPath("$.totalClicks").value(0))
                .andExpect(jsonPath("$.lastAccessedAt").value(nullValue()))
                .andExpect(jsonPath("$.dailyClicks").isEmpty());
        mvc.perform(get("/" + code)).andExpect(status().isFound())
                .andExpect(header().string("Location", result.originalUrl()));
        mvc.perform(get("/api/v1/urls/" + code + "/stats")).andExpect(status().isOk())
                .andExpect(jsonPath("$.totalClicks").value(1))
                .andExpect(jsonPath("$.lastAccessedAt").value(NOW.toString()))
                .andExpect(jsonPath("$.dailyClicks[0].date").value("2026-01-01"))
                .andExpect(jsonPath("$.dailyClicks[0].clicks").value(1));
        for (int i = 0; i < 2; i++) {
            mvc.perform(patch("/api/v1/urls/" + code + "/disable")).andExpect(status().isOk())
                    .andExpect(jsonPath("$.status").value("DISABLED"));
        }
        mvc.perform(get("/" + code)).andExpect(status().isGone())
                .andExpect(jsonPath("$.code").value("URL_DISABLED"));
        assertThat(analytics.stats(code).totalClicks()).isEqualTo(1);
        assertThat(urlRepository.count()).isEqualTo(1);
    }

    @Test
    void expiresAtExactBoundaryAndDoesNotRecordRejectedClick() throws Exception {
        var link = urls.create(new CreateUrlRequest("https://example.com", NOW.plusSeconds(60)));
        clock.advance(Duration.ofSeconds(59));
        mvc.perform(get("/" + link.shortCode())).andExpect(status().isFound());
        clock.advance(Duration.ofSeconds(1));
        mvc.perform(get("/" + link.shortCode())).andExpect(status().isGone())
                .andExpect(jsonPath("$.code").value("URL_EXPIRED"));
        assertThat(urls.get(link.shortCode()).status()).isEqualTo(UrlStatus.EXPIRED);
        assertThat(analytics.stats(link.shortCode()).totalClicks()).isEqualTo(1);
    }

    @Test
    void aggregatesDaysInUtcWithCorrectLastAccess() {
        var link = urls.create(new CreateUrlRequest("https://example.com", null));
        redirects.redirect(link.shortCode());
        redirects.redirect(link.shortCode());
        clock.advance(Duration.ofDays(1));
        redirects.redirect(link.shortCode());
        var stats = analytics.stats(link.shortCode());
        assertThat(stats.totalClicks()).isEqualTo(3);
        assertThat(stats.lastAccessedAt()).isEqualTo(NOW.plus(Duration.ofDays(1)));
        assertThat(stats.dailyClicks()).extracting(DailyClickResponse::clicks).containsExactly(2L, 1L);
        assertThat(stats.dailyClicks()).extracting(d -> d.date().toString()).containsExactly("2026-01-01", "2026-01-02");
    }

    @Test
    void badInputsMissingCodesAndHeadDoNotWrite() throws Exception {
        for (String body : new String[]{"{}", "{\"originalUrl\":\"ftp://example.com\"}",
                "{\"originalUrl\":\"https://example.com\",\"expiresAt\":\"2026-01-01T12:00:00Z\"}"}) {
            mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON).content(body))
                    .andExpect(status().isBadRequest());
        }
        for (String path : new String[]{"/missing", "/bad", "/api/v1/urls/missing",
                "/api/v1/urls/missing/stats"}) {
            mvc.perform(get(path)).andExpect(status().isNotFound());
        }
        mvc.perform(patch("/api/v1/urls/missing/disable")).andExpect(status().isNotFound());
        var link = urls.create(new CreateUrlRequest("https://example.com", null));
        mvc.perform(head("/" + link.shortCode())).andExpect(status().isMethodNotAllowed());
        assertThat(clickRepository.count()).isZero();
        assertThat(urlRepository.count()).isEqualTo(1);
    }

    @Test
    void exposesHealthAndOpenApi() throws Exception {
        mvc.perform(get("/actuator/health")).andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components").doesNotExist());
        mvc.perform(get("/actuator/health/readiness")).andExpect(status().isOk());
        mvc.perform(get("/v3/api-docs")).andExpect(status().isOk())
                .andExpect(jsonPath("$.info.title").value("URL Shortener API"))
                .andExpect(jsonPath("$.paths['/api/v1/urls'].post").exists());
        mvc.perform(get("/swagger-ui/index.html")).andExpect(status().isOk());
    }
}
