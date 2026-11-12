package com.varun.shortener.integration;

import static org.assertj.core.api.Assertions.*;
import com.varun.shortener.dto.CreateUrlRequest;
import com.varun.shortener.exception.*;
import com.varun.shortener.support.PostgresIntegrationTest;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class ConcurrentRequestsIT extends PostgresIntegrationTest {
    @Test
    void concurrentRedirectsDoNotLoseClicks() throws Exception {
        var link = urls.create(new CreateUrlRequest("https://example.com", null));
        try (var executor = Executors.newFixedThreadPool(12)) {
            var jobs = new ArrayList<Callable<String>>();
            for (int i = 0; i < 100; i++) jobs.add(() -> redirects.redirect(link.shortCode()));
            for (var result : executor.invokeAll(jobs)) assertThat(result.get(15, TimeUnit.SECONDS)).isEqualTo(link.originalUrl());
        }
        var stats = analytics.stats(link.shortCode());
        assertThat(stats.totalClicks()).isEqualTo(100);
        assertThat(stats.dailyClicks().getFirst().clicks()).isEqualTo(100);
        assertThat(clickRepository.count()).isEqualTo(100);
    }

    @Test
    void simultaneousCreateRequestsPersistDistinctCodes() throws Exception {
        try (var executor = Executors.newFixedThreadPool(12)) {
            var jobs = new ArrayList<Callable<String>>();
            for (int i = 0; i < 50; i++) jobs.add(() -> urls.create(new CreateUrlRequest("https://example.com", null)).shortCode());
            var codes = new HashSet<String>();
            for (var result : executor.invokeAll(jobs)) assertThat(codes.add(result.get(15, TimeUnit.SECONDS))).isTrue();
        }
        assertThat(urlRepository.count()).isEqualTo(50);
    }

    @Test
    void disableRacingRedirectsCountsOnlyAcceptedRequests() throws Exception {
        var link = urls.create(new CreateUrlRequest("https://example.com", null));
        var start = new CountDownLatch(1);
        try (var executor = Executors.newFixedThreadPool(12)) {
            var futures = new ArrayList<Future<Boolean>>();
            for (int i = 0; i < 40; i++) futures.add(executor.submit(() -> {
                start.await();
                try { redirects.redirect(link.shortCode()); return true; }
                catch (ApiException ex) {
                    assertThat(ex.code()).isEqualTo(ErrorCode.URL_DISABLED);
                    return false;
                }
            }));
            var disabled = executor.submit(() -> { start.await(); return urls.disable(link.shortCode()); });
            start.countDown();
            disabled.get(15, TimeUnit.SECONDS);
            int accepted = 0;
            for (var future : futures) if (future.get(15, TimeUnit.SECONDS)) accepted++;
            assertThat(analytics.stats(link.shortCode()).totalClicks()).isEqualTo(accepted);
        }
        assertThatThrownBy(() -> redirects.redirect(link.shortCode())).isInstanceOfSatisfying(ApiException.class,
                ex -> assertThat(ex.code()).isEqualTo(ErrorCode.URL_DISABLED));
    }
}
