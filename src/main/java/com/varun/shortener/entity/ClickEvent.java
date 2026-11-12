package com.varun.shortener.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "click_events")
public class ClickEvent {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "url_id", nullable = false, updatable = false)
    private ShortUrl url;
    @Column(name = "accessed_at", nullable = false, updatable = false)
    private Instant accessedAt;

    protected ClickEvent() {}
    public ClickEvent(ShortUrl url, Instant accessedAt) {
        this.url = url;
        this.accessedAt = accessedAt;
    }

    public Long getId() { return id; }
    public ShortUrl getUrl() { return url; }
    public Instant getAccessedAt() { return accessedAt; }
}
