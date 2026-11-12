package com.varun.shortener.analytics;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.varun.shortener.configuration.ShortenerProperties;
import com.varun.shortener.entity.ShortUrl;
import com.varun.shortener.mapper.UrlMapper;
import com.varun.shortener.repository.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

class AnalyticsServiceTest {
    @Test
    void returnsEmptyAnalyticsWithNullLastAccess() {
        var now = Instant.parse("2026-01-01T00:00:00Z");
        var url = new ShortUrl("abc1234", "https://example.com", now, null);
        ReflectionTestUtils.setField(url, "id", 1L);
        var urls = mock(UrlRepository.class);
        var clicks = mock(ClickEventRepository.class);
        when(urls.findByShortCode("abc1234")).thenReturn(Optional.of(url));
        when(clicks.summarize(1L)).thenReturn(new ClickSummary(0, null));
        when(clicks.dailyCounts(1L)).thenReturn(List.of());
        var service = new AnalyticsService(urls, clicks, new UrlMapper(new ShortenerProperties("http://localhost:8080")),
                Clock.fixed(now, ZoneOffset.UTC));
        var result = service.stats("abc1234");
        assertThat(result.totalClicks()).isZero();
        assertThat(result.lastAccessedAt()).isNull();
        assertThat(result.dailyClicks()).isEmpty();
        assertThat(result.createdAt()).isEqualTo(now);
    }
}
