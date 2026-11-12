package com.varun.shortener.service;

import com.varun.shortener.dto.*;
import com.varun.shortener.exception.*;
import com.varun.shortener.mapper.UrlMapper;
import com.varun.shortener.repository.UrlRepository;
import java.time.Clock;
import java.time.temporal.ChronoUnit;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UrlService {
    private static final int MAX_COLLISION_RETRIES = 5;
    private final UrlRepository urls;
    private final ShortCodeGenerator generator;
    private final UrlMapper mapper;
    private final Clock clock;

    public UrlService(UrlRepository urls, ShortCodeGenerator generator, UrlMapper mapper, Clock clock) {
        this.urls = urls; this.generator = generator; this.mapper = mapper; this.clock = clock;
    }

    @Transactional(timeout = 5)
    public UrlResponse create(CreateUrlRequest request) {
        var now = clock.instant().truncatedTo(ChronoUnit.MICROS);
        var expires = request.expiresAt() == null ? null : request.expiresAt().truncatedTo(ChronoUnit.MICROS);
        if (expires != null && !expires.isAfter(now)) throw new ApiException(ErrorCode.INVALID_REQUEST);
        for (int attempt = 0; attempt <= MAX_COLLISION_RETRIES; attempt++) {
            String code = generator.generate();
            // A collision does not abort the PostgreSQL transaction; other DB errors propagate.
            if (urls.insertIfAvailable(code, request.originalUrl(), now, expires) == 1) {
                return mapper.toResponse(urls.findByShortCode(code).orElseThrow(), now);
            }
        }
        throw new ApiException(ErrorCode.CODE_GENERATION_EXHAUSTED);
    }

    @Transactional(readOnly = true, timeout = 5)
    public UrlResponse get(String code) {
        validateCode(code);
        var url = urls.findByShortCode(code).orElseThrow(() -> new ApiException(ErrorCode.URL_NOT_FOUND));
        return mapper.toResponse(url, clock.instant());
    }

    @Transactional(timeout = 5)
    public UrlResponse disable(String code) {
        validateCode(code);
        var url = urls.findForDisable(code).orElseThrow(() -> new ApiException(ErrorCode.URL_NOT_FOUND));
        url.disable();
        return mapper.toResponse(url, clock.instant());
    }

    public static void validateCode(String code) {
        if (code == null || !code.matches("[A-Za-z0-9]{7}")) throw new ApiException(ErrorCode.URL_NOT_FOUND);
    }
}
