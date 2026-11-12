package com.varun.shortener.web;

import static org.assertj.core.api.Assertions.*;
import com.varun.shortener.support.MutableClock;
import java.time.*;
import java.util.ArrayList;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class InMemoryRateLimiterTest {
    MutableClock clock = new MutableClock(Instant.parse("2026-01-01T00:00:00Z"));

    @Test
    void enforcesRollingWindowAndIndependentIps() {
        var limiter = new InMemoryRateLimiter(clock);
        for (int i = 0; i < 100; i++) assertThat(limiter.acquire("one").allowed()).isTrue();
        assertThat(limiter.acquire("one").retryAfterSeconds()).isEqualTo(3600);
        assertThat(limiter.acquire("two").allowed()).isTrue();
        clock.advance(Duration.ofMinutes(59));
        assertThat(limiter.acquire("one").allowed()).isFalse();
        clock.advance(Duration.ofMinutes(1));
        assertThat(limiter.acquire("one").allowed()).isTrue();
    }

    @Test
    void simultaneousRequestsCannotOvershootLimit() throws Exception {
        var limiter = new InMemoryRateLimiter(clock);
        try (var executor = Executors.newFixedThreadPool(16)) {
            var jobs = new ArrayList<Callable<Boolean>>();
            for (int i = 0; i < 500; i++) jobs.add(() -> limiter.acquire("one").allowed());
            long accepted = 0;
            for (var future : executor.invokeAll(jobs)) if (future.get()) accepted++;
            assertThat(accepted).isEqualTo(100);
        }
    }

    @Test
    void doesNotEvictActiveClientsToBypassLimitAndReclaimsIdleEntries() {
        var limiter = new InMemoryRateLimiter(clock, 1, 1);
        assertThat(limiter.acquire("one").allowed()).isTrue();
        assertThat(limiter.acquire("two").atCapacity()).isTrue();
        assertThat(limiter.acquire("one").allowed()).isFalse();
        clock.advance(Duration.ofHours(1));
        limiter.cleanup();
        assertThat(limiter.acquire("two").allowed()).isTrue();
    }
}
