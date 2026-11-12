package com.varun.shortener.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "urls")
public class ShortUrl {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "short_code", nullable = false, unique = true, length = 7, updatable = false)
    private String shortCode;
    @Column(name = "original_url", nullable = false, length = 2048, updatable = false)
    private String originalUrl;
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;
    @Column(name = "expires_at", updatable = false)
    private Instant expiresAt;
    @Column(nullable = false)
    private boolean disabled;

    protected ShortUrl() {}

    public ShortUrl(String shortCode, String originalUrl, Instant createdAt, Instant expiresAt) {
        this.shortCode = shortCode;
        this.originalUrl = originalUrl;
        this.createdAt = createdAt;
        this.expiresAt = expiresAt;
    }

    public Long getId() { return id; }
    public String getShortCode() { return shortCode; }
    public String getOriginalUrl() { return originalUrl; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getExpiresAt() { return expiresAt; }
    public boolean isDisabled() { return disabled; }
    public void disable() { disabled = true; }

    public UrlStatus statusAt(Instant now) {
        if (disabled) return UrlStatus.DISABLED;
        return expiresAt != null && !now.isBefore(expiresAt) ? UrlStatus.EXPIRED : UrlStatus.ACTIVE;
    }
}
