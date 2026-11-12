package com.varun.shortener.web;

import static org.hamcrest.Matchers.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.varun.shortener.analytics.AnalyticsService;
import com.varun.shortener.controller.*;
import com.varun.shortener.dto.UrlResponse;
import com.varun.shortener.entity.UrlStatus;
import com.varun.shortener.exception.*;
import com.varun.shortener.service.*;
import java.time.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.*;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest({UrlController.class, RedirectController.class})
@Import({ApiProblemFactory.class, InMemoryRateLimiter.class, ApiContractTest.TimeConfiguration.class})
class ApiContractTest {
    @Autowired MockMvc mvc;
    @MockitoBean UrlService urls;
    @MockitoBean RedirectService redirects;
    @MockitoBean AnalyticsService analytics;

    @TestConfiguration
    static class TimeConfiguration {
        @Bean Clock clock() { return Clock.fixed(Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC); }
    }

    @Test
    void creationUsesExactContractAndIncludesNullExpiration() throws Exception {
        when(urls.create(any())).thenReturn(new UrlResponse("abc1234", "http://localhost:8080/abc1234",
                "https://example.com", Instant.parse("2026-01-01T00:00:00Z"), null, UrlStatus.ACTIVE));
        mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON)
                .content(""" 
                        {"originalUrl":"https://example.com"}
                        """))
                .andExpect(status().isCreated()).andExpect(header().string("Location", "/api/v1/urls/abc1234"))
                .andExpect(jsonPath("$.shortCode").value("abc1234"))
                .andExpect(jsonPath("$.shortUrl").value("http://localhost:8080/abc1234"))
                .andExpect(jsonPath("$.originalUrl").value("https://example.com"))
                .andExpect(jsonPath("$.createdAt").value("2026-01-01T00:00:00Z"))
                .andExpect(jsonPath("$.expiresAt").value(nullValue()))
                .andExpect(jsonPath("$.status").value("ACTIVE"))
                .andExpect(jsonPath("$", aMapWithSize(6)));
    }

    @Test
    void invalidInputProducesSafeProblemDetails() throws Exception {
        mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON)
                .content("{\"originalUrl\":\"javascript:secret-value\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(header().exists("X-Request-Id"))
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.errors[0].field").value("originalUrl"))
                .andExpect(content().string(not(containsString("secret-value"))));
        verifyNoInteractions(urls);
    }

    @Test
    void malformedJsonAndUnknownFieldsAreRejected() throws Exception {
        for (String body : new String[]{"{", "{\"originalUrl\":\"https://example.com\",\"admin\":true}",
                "{\"originalUrl\":\"https://example.com\",\"expiresAt\":\"tomorrow\"}", "{}"}) {
            mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON).content(body))
                    .andExpect(status().isBadRequest())
                    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON));
        }
        verifyNoInteractions(urls);
    }

    @Test
    void redirectUses302LocationAndNoStore() throws Exception {
        when(redirects.redirect("abc1234")).thenReturn("https://example.com/path?a=1");
        mvc.perform(get("/abc1234")).andExpect(status().isFound())
                .andExpect(header().string("Location", "https://example.com/path?a=1"))
                .andExpect(header().string("Cache-Control", "no-store"));
    }

    @Test
    void headDoesNotRecordAnAnalyticsEvent() throws Exception {
        mvc.perform(head("/abc1234")).andExpect(status().isMethodNotAllowed())
                .andExpect(header().string("Allow", "GET"));
        verifyNoInteractions(redirects);
    }

    @Test
    void goneAndMissingResponsesHaveStableCodes() throws Exception {
        when(redirects.redirect("abc1234")).thenThrow(new ApiException(ErrorCode.URL_DISABLED));
        mvc.perform(get("/abc1234")).andExpect(status().isGone())
                .andExpect(jsonPath("$.code").value("URL_DISABLED"));
        when(urls.get("missing")).thenThrow(new ApiException(ErrorCode.URL_NOT_FOUND));
        mvc.perform(get("/api/v1/urls/missing")).andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("URL_NOT_FOUND"));
    }

    @Test
    void databaseFailuresAreSanitizedAndDoNotRedirect() throws Exception {
        when(redirects.redirect("abc1234")).thenThrow(new DataAccessResourceFailureException("password=secret"));
        mvc.perform(get("/abc1234")).andExpect(status().isServiceUnavailable())
                .andExpect(header().doesNotExist("Location"))
                .andExpect(jsonPath("$.code").value("DATABASE_UNAVAILABLE"))
                .andExpect(content().string(not(containsString("secret"))));
    }

    @Test
    void unexpectedErrorsAreSanitized() throws Exception {
        when(urls.get("abc1234")).thenThrow(new IllegalStateException("private data"));
        mvc.perform(get("/api/v1/urls/abc1234")).andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(content().string(not(containsString("private data"))));
    }

    @Test
    void unsupportedMediaTypeIsAProblemResponse() throws Exception {
        mvc.perform(post("/api/v1/urls").contentType(MediaType.TEXT_PLAIN).content("invalid"))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.code").value("HTTP_415"));
    }
}
