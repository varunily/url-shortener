package com.varun.shortener.dto;

import com.varun.shortener.entity.UrlStatus;
import java.time.Instant;
import java.util.List;

public record UrlStatsResponse(String shortCode, String shortUrl, String originalUrl,
                               Instant createdAt, Instant expiresAt, UrlStatus status,
                               long totalClicks, Instant lastAccessedAt,
                               List<DailyClickResponse> dailyClicks) {}
