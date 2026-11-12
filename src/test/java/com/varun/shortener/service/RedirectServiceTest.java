package com.varun.shortener.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.varun.shortener.entity.*;
import com.varun.shortener.exception.*;
import com.varun.shortener.repository.*;
import java.time.*;
import java.util.Optional;
import org.junit.jupiter.api.*;
import org.mockito.ArgumentCaptor;

class RedirectServiceTest {
    private static final Instant NOW = Instant.parse("2026-01-01T00:00:00Z");
    UrlRepository urls = mock(UrlRepository.class);
    ClickEventRepository clicks = mock(ClickEventRepository.class);
    RedirectService service = new RedirectService(urls, clicks, Clock.fixed(NOW, ZoneOffset.UTC));

    @Test
    void recordsOneClickAtCurrentTimeBeforeReturningTarget() {
        var url = new ShortUrl("abc1234", "https://example.com", NOW, null);
        when(urls.findForRedirect("abc1234")).thenReturn(Optional.of(url));
        assertThat(service.redirect("abc1234")).isEqualTo(url.getOriginalUrl());
        var event = ArgumentCaptor.forClass(ClickEvent.class);
        verify(clicks).save(event.capture());
        assertThat(event.getValue().getAccessedAt()).isEqualTo(NOW);
        assertThat(event.getValue().getUrl()).isSameAs(url);
    }

    @Test
    void expirationAtExactBoundaryDoesNotRecordClick() {
        var url = new ShortUrl("abc1234", "https://example.com", NOW.minusSeconds(1), NOW);
        when(urls.findForRedirect("abc1234")).thenReturn(Optional.of(url));
        assertThatThrownBy(() -> service.redirect("abc1234")).isInstanceOfSatisfying(ApiException.class,
                ex -> assertThat(ex.code()).isEqualTo(ErrorCode.URL_EXPIRED));
        verifyNoInteractions(clicks);
    }

    @Test
    void disabledLinkDoesNotRecordClick() {
        var url = new ShortUrl("abc1234", "https://example.com", NOW, null);
        url.disable();
        when(urls.findForRedirect("abc1234")).thenReturn(Optional.of(url));
        assertThatThrownBy(() -> service.redirect("abc1234")).isInstanceOfSatisfying(ApiException.class,
                ex -> assertThat(ex.code()).isEqualTo(ErrorCode.URL_DISABLED));
        verifyNoInteractions(clicks);
    }

    @Test
    void unknownLinkDoesNotRecordClick() {
        when(urls.findForRedirect("abc1234")).thenReturn(Optional.empty());
        assertThatThrownBy(() -> service.redirect("abc1234")).isInstanceOf(ApiException.class);
        verifyNoInteractions(clicks);
    }
}
