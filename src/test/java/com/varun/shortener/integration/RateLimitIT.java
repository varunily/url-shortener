package com.varun.shortener.integration;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.varun.shortener.support.PostgresIntegrationTest;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

class RateLimitIT extends PostgresIntegrationTest {
    @Test
    void limitsPostOnlyAndIgnoresSpoofedForwardedHeaders() throws Exception {
        String code = null;
        for (int i = 0; i < 100; i++) {
            var response = mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON)
                    .content("{\"originalUrl\":\"https://example.com\"}")
                    .header("X-Forwarded-For", "192.0.2." + i))
                    .andExpect(status().isCreated()).andReturn().getResponse();
            code = json.readTree(response.getContentAsString()).get("shortCode").asText();
        }
        mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON)
                .content("{\"originalUrl\":\"https://example.com\"}").header("X-Forwarded-For", "198.51.100.1"))
                .andExpect(status().isTooManyRequests()).andExpect(header().string("Retry-After", "3600"))
                .andExpect(jsonPath("$.code").value("RATE_LIMIT_EXCEEDED"))
                .andExpect(jsonPath("$.requestId").isNotEmpty());
        mvc.perform(get("/" + code)).andExpect(status().isFound());
        mvc.perform(get("/api/v1/urls/" + code + "/stats")).andExpect(status().isOk());
        mvc.perform(patch("/api/v1/urls/" + code + "/disable")).andExpect(status().isOk());
        mvc.perform(post("/api/v1/urls").with(r -> { r.setRemoteAddr("192.0.2.200"); return r; })
                .contentType(MediaType.APPLICATION_JSON).content("{\"originalUrl\":\"https://example.com\"}"))
                .andExpect(status().isCreated());
        clock.advance(Duration.ofHours(1));
        mvc.perform(post("/api/v1/urls").contentType(MediaType.APPLICATION_JSON)
                .content("{\"originalUrl\":\"https://example.com\"}")).andExpect(status().isCreated());
        assertThat(urlRepository.count()).isEqualTo(102);
    }
}
