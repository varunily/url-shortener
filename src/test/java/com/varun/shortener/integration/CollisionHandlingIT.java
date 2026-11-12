package com.varun.shortener.integration;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.varun.shortener.dto.CreateUrlRequest;
import com.varun.shortener.exception.*;
import com.varun.shortener.service.ShortCodeGenerator;
import com.varun.shortener.support.PostgresIntegrationTest;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

class CollisionHandlingIT extends PostgresIntegrationTest {
    @MockitoBean ShortCodeGenerator generator;

    @Test
    void collisionDoesNotPoisonTransactionAndSixthAttemptCanSucceed() {
        jdbc.update("INSERT INTO urls(short_code, original_url, created_at) VALUES ('old1234', 'https://old.example', ?)",
                Timestamp.from(NOW));
        when(generator.generate()).thenReturn("old1234", "old1234", "old1234", "old1234", "old1234", "new1234");
        var result = urls.create(new CreateUrlRequest("https://new.example", null));
        assertThat(result.shortCode()).isEqualTo("new1234");
        assertThat(urlRepository.count()).isEqualTo(2);
        verify(generator, times(6)).generate();
    }

    @Test
    void exhaustionRollsBackWithoutOverwritingExistingMapping() {
        jdbc.update("INSERT INTO urls(short_code, original_url, created_at) VALUES ('old1234', 'https://old.example', ?)",
                Timestamp.from(NOW));
        when(generator.generate()).thenReturn("old1234");
        assertThatThrownBy(() -> urls.create(new CreateUrlRequest("https://new.example", null)))
                .isInstanceOfSatisfying(ApiException.class,
                        ex -> assertThat(ex.code()).isEqualTo(ErrorCode.CODE_GENERATION_EXHAUSTED));
        assertThat(urlRepository.count()).isEqualTo(1);
        assertThat(urls.get("old1234").originalUrl()).isEqualTo("https://old.example");
        verify(generator, times(6)).generate();
    }

    @Test
    void concurrentCreatorsResolveTheSameCandidateSafely() throws Exception {
        var index = new AtomicInteger();
        var firstCandidates = new CountDownLatch(2);
        when(generator.generate()).thenAnswer(call -> {
            int n = index.getAndIncrement();
            if (n < 2) {
                firstCandidates.countDown();
                if (!firstCandidates.await(3, TimeUnit.SECONDS)) throw new AssertionError("Creator did not reach barrier");
                return "same123";
            }
            return "next123";
        });
        try (var executor = Executors.newFixedThreadPool(2)) {
            var jobs = new ArrayList<Callable<String>>();
            for (int i = 0; i < 2; i++) jobs.add(() -> urls.create(new CreateUrlRequest("https://example.com", null)).shortCode());
            var codes = new ArrayList<String>();
            for (var future : executor.invokeAll(jobs)) codes.add(future.get(10, TimeUnit.SECONDS));
            assertThat(codes).containsExactlyInAnyOrder("same123", "next123");
        }
        assertThat(urlRepository.count()).isEqualTo(2);
    }
}
