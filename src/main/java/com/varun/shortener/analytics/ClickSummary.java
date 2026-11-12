package com.varun.shortener.analytics;

import java.time.Instant;

public record ClickSummary(long totalClicks, Instant lastAccessedAt) {}
