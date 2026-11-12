package com.varun.shortener.configuration;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("shortener")
public record ShortenerProperties(String baseUrl) {
    public ShortenerProperties {
        URI uri;
        try {
            uri = URI.create(baseUrl);
        } catch (RuntimeException ex) {
            throw new IllegalArgumentException("BASE_URL must be an absolute HTTP(S) origin");
        }
        if (uri.getHost() == null || !("http".equalsIgnoreCase(uri.getScheme())
                || "https".equalsIgnoreCase(uri.getScheme())) || uri.getUserInfo() != null
                || uri.getQuery() != null || uri.getFragment() != null
                || !(uri.getPath().isEmpty() || "/".equals(uri.getPath()))
                || uri.getPort() == 0 || uri.getPort() > 65535) {
            throw new IllegalArgumentException("BASE_URL must be an absolute HTTP(S) origin");
        }
        baseUrl = baseUrl.replaceAll("/+$", "");
    }
}
