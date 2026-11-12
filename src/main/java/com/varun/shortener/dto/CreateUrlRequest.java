package com.varun.shortener.dto;

import com.varun.shortener.validation.HttpUrl;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Instant;

public record CreateUrlRequest(
        @NotBlank @Size(max = 2048) @HttpUrl String originalUrl,
        Instant expiresAt) {}
