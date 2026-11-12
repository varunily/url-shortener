package com.varun.shortener.dto;

import com.varun.shortener.entity.UrlStatus;
import java.time.Instant;

public record UrlResponse(String shortCode, String shortUrl, String originalUrl,
                          Instant createdAt, Instant expiresAt, UrlStatus status) {}
