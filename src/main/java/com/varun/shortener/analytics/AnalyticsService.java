package com.varun.shortener.analytics;

import com.varun.shortener.dto.*;
import com.varun.shortener.exception.*;
import com.varun.shortener.mapper.UrlMapper;
import com.varun.shortener.repository.*;
import com.varun.shortener.service.UrlService;
import java.time.Clock;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

@Service
public class AnalyticsService {
    private final UrlRepository urls;
    private final ClickEventRepository clicks;
    private final UrlMapper mapper;
    private final Clock clock;

    public AnalyticsService(UrlRepository urls, ClickEventRepository clicks, UrlMapper mapper, Clock clock) {
        this.urls = urls; this.clicks = clicks; this.mapper = mapper; this.clock = clock;
    }

    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ, timeout = 5)
    public UrlStatsResponse stats(String code) {
        UrlService.validateCode(code);
        var url = urls.findByShortCode(code).orElseThrow(() -> new ApiException(ErrorCode.URL_NOT_FOUND));
        var metadata = mapper.toResponse(url, clock.instant());
        var summary = clicks.summarize(url.getId());
        var daily = clicks.dailyCounts(url.getId()).stream()
                .map(day -> new DailyClickResponse(day.getDate(), day.getClicks())).toList();
        return new UrlStatsResponse(metadata.shortCode(), metadata.shortUrl(), metadata.originalUrl(),
                metadata.createdAt(), metadata.expiresAt(), metadata.status(),
                summary.totalClicks(), summary.lastAccessedAt(), daily);
    }
}
