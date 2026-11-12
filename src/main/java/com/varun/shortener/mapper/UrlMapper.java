package com.varun.shortener.mapper;

import com.varun.shortener.configuration.ShortenerProperties;
import com.varun.shortener.dto.UrlResponse;
import com.varun.shortener.entity.ShortUrl;
import java.time.Instant;
import org.springframework.stereotype.Component;

@Component
public class UrlMapper {
    private final ShortenerProperties properties;
    public UrlMapper(ShortenerProperties properties) { this.properties = properties; }

    public UrlResponse toResponse(ShortUrl url, Instant now) {
        return new UrlResponse(url.getShortCode(), properties.baseUrl() + "/" + url.getShortCode(),
                url.getOriginalUrl(), url.getCreatedAt(), url.getExpiresAt(), url.statusAt(now));
    }
}
