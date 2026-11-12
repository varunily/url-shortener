package com.varun.shortener.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.varun.shortener.configuration.ShortenerProperties;
import com.varun.shortener.dto.CreateUrlRequest;
import com.varun.shortener.entity.*;
import com.varun.shortener.exception.*;
import com.varun.shortener.mapper.UrlMapper;
import com.varun.shortener.repository.UrlRepository;
import java.time.*;
import java.util.Optional;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataAccessResourceFailureException;

@ExtendWith(MockitoExtension.class)
class UrlServiceTest {
    private static final Instant NOW = Instant.parse("2026-01-01T00:00:00Z");
    @Mock UrlRepository urls;
    @Mock ShortCodeGenerator generator;
    UrlService service;
    CreateUrlRequest request = new CreateUrlRequest("https://example.com", null);

    @BeforeEach
    void setup() {
        service = new UrlService(urls, generator, new UrlMapper(new ShortenerProperties("http://localhost:8080/")),
                Clock.fixed(NOW, ZoneOffset.UTC));
    }

    @Test
    void createsAndMapsThePersistedRecord() {
        when(generator.generate()).thenReturn("abc1234");
        when(urls.insertIfAvailable("abc1234", request.originalUrl(), NOW, null)).thenReturn(1);
        when(urls.findByShortCode("abc1234")).thenReturn(Optional.of(new ShortUrl("abc1234", request.originalUrl(), NOW, null)));
        var result = service.create(request);
        assertThat(result.shortUrl()).isEqualTo("http://localhost:8080/abc1234");
        assertThat(result.status()).isEqualTo(UrlStatus.ACTIVE);
        assertThat(result.createdAt()).isEqualTo(NOW);
        assertThat(result.expiresAt()).isNull();
    }

    @Test
    void retriesCollisionAndSucceeds() {
        when(generator.generate()).thenReturn("old1234", "new1234");
        when(urls.insertIfAvailable(anyString(), anyString(), eq(NOW), isNull())).thenReturn(0, 1);
        when(urls.findByShortCode("new1234")).thenReturn(Optional.of(new ShortUrl("new1234", request.originalUrl(), NOW, null)));
        assertThat(service.create(request).shortCode()).isEqualTo("new1234");
        verify(generator, times(2)).generate();
    }

    @Test
    void permitsExactlyFiveRetriesAfterInitialAttempt() {
        when(generator.generate()).thenReturn("old1234");
        assertThatThrownBy(() -> service.create(request)).isInstanceOfSatisfying(ApiException.class,
                ex -> assertThat(ex.code()).isEqualTo(ErrorCode.CODE_GENERATION_EXHAUSTED));
        verify(generator, times(6)).generate();
        verify(urls, times(6)).insertIfAvailable(anyString(), anyString(), eq(NOW), isNull());
    }

    @Test
    void doesNotRetryUnrelatedDatabaseFailures() {
        when(generator.generate()).thenReturn("abc1234");
        when(urls.insertIfAvailable(anyString(), anyString(), eq(NOW), isNull()))
                .thenThrow(new DataAccessResourceFailureException("database unavailable"));
        assertThatThrownBy(() -> service.create(request)).isInstanceOf(DataAccessResourceFailureException.class);
        verify(generator).generate();
    }

    @Test
    void rejectsExpirationAtOrBeforeCreation() {
        for (Instant expiration : new Instant[]{NOW, NOW.minusSeconds(1)}) {
            assertThatThrownBy(() -> service.create(new CreateUrlRequest(request.originalUrl(), expiration)))
                    .isInstanceOf(ApiException.class);
        }
        verifyNoInteractions(urls, generator);
    }

    @Test
    void disablingIsIdempotentAndOverridesExpiredStatus() {
        var url = new ShortUrl("abc1234", request.originalUrl(), NOW.minusSeconds(2), NOW.minusSeconds(1));
        when(urls.findForDisable("abc1234")).thenReturn(Optional.of(url));
        assertThat(service.disable("abc1234").status()).isEqualTo(UrlStatus.DISABLED);
        assertThat(service.disable("abc1234").status()).isEqualTo(UrlStatus.DISABLED);
    }

    @Test
    void rejectsMalformedCodesBeforeQueryingDatabase() {
        assertThatThrownBy(() -> service.get("!")).isInstanceOf(ApiException.class);
        verifyNoInteractions(urls);
    }
}
