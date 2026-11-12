package com.varun.shortener.web;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.varun.shortener.exception.ApiProblemFactory;
import jakarta.servlet.FilterChain;
import java.time.Clock;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mock.web.*;

class CreationRateLimitFilterTest {
    @ParameterizedTest
    @ValueSource(strings = {"/api/v1/urls", "/api/v1/urls;tracking=1", "/api/v1/%75rls", "//api/v1/urls"})
    void alternatePathRepresentationsStillConsumeQuota(String path) throws Exception {
        var limiter = mock(InMemoryRateLimiter.class);
        when(limiter.acquire(anyString())).thenReturn(new InMemoryRateLimiter.Decision(true, false, 0));
        var filter = new CreationRateLimitFilter(limiter, new ApiProblemFactory(Clock.systemUTC()), new ObjectMapper());
        var request = new MockHttpServletRequest("POST", path);
        var chain = mock(FilterChain.class);
        filter.doFilter(request, new MockHttpServletResponse(), chain);
        verify(limiter).acquire("127.0.0.1");
        verify(chain).doFilter(any(), any());
    }
}
