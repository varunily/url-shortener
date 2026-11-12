package com.varun.shortener.integration;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.varun.shortener.dto.CreateUrlRequest;
import com.varun.shortener.entity.ClickEvent;
import com.varun.shortener.repository.ClickEventRepository;
import com.varun.shortener.support.PostgresIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

class AnalyticsFailureIT extends PostgresIntegrationTest {
    @MockitoSpyBean ClickEventRepository eventRepository;

    @Test
    void writeFailureRollsBackInsertedEventAndPreventsRedirect() throws Exception {
        var link = urls.create(new CreateUrlRequest("https://example.com", null));
        doAnswer(call -> {
            ClickEvent event = call.getArgument(0);
            // JdbcTemplate joins the service's real transaction; then inject a write failure.
            jdbc.update("INSERT INTO click_events(url_id, accessed_at) VALUES (?, ?)",
                    event.getUrl().getId(), java.sql.Timestamp.from(event.getAccessedAt()));
            throw new DataIntegrityViolationException("simulated failure after insert; sensitive details");
        }).when(eventRepository).save(any(ClickEvent.class));
        mvc.perform(get("/" + link.shortCode())).andExpect(status().isServiceUnavailable())
                .andExpect(header().doesNotExist("Location"))
                .andExpect(jsonPath("$.code").value("DATABASE_UNAVAILABLE"));
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM click_events", Long.class)).isZero();
        reset(eventRepository);
        mvc.perform(get("/" + link.shortCode())).andExpect(status().isFound());
        assertThat(analytics.stats(link.shortCode()).totalClicks()).isEqualTo(1);
    }
}
