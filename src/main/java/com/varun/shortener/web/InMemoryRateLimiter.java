package com.varun.shortener.web;

import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class InMemoryRateLimiter {
    private static final Duration WINDOW = Duration.ofHours(1);
    private final Map<String, ArrayDeque<Instant>> requests = new HashMap<>();
    private final Clock clock;
    private final int limit;
    private final int maxClients;

    @Autowired
    public InMemoryRateLimiter(Clock clock) { this(clock, 100, 10_000); }

    InMemoryRateLimiter(Clock clock, int limit, int maxClients) {
        this.clock = clock; this.limit = limit; this.maxClients = maxClients;
    }

    public record Decision(boolean allowed, boolean atCapacity, long retryAfterSeconds) {}

    public synchronized Decision acquire(String ip) {
        var now = clock.instant();
        var entries = requests.get(ip);
        if (entries == null) {
            if (requests.size() >= maxClients) cleanupAt(now);
            if (requests.size() >= maxClients) return new Decision(false, true, 60);
            entries = new ArrayDeque<>();
            requests.put(ip, entries);
        }
        prune(entries, now);
        if (entries.size() >= limit) {
            long millis = Duration.between(now, entries.getFirst().plus(WINDOW)).toMillis();
            return new Decision(false, false, Math.max(1, (millis + 999) / 1000));
        }
        entries.addLast(now);
        return new Decision(true, false, 0);
    }

    @Scheduled(fixedDelay = 60_000)
    public synchronized void cleanup() { cleanupAt(clock.instant()); }

    private void cleanupAt(Instant now) {
        requests.values().removeIf(entries -> { prune(entries, now); return entries.isEmpty(); });
    }

    private void prune(ArrayDeque<Instant> entries, Instant now) {
        var cutoff = now.minus(WINDOW);
        while (!entries.isEmpty() && !entries.getFirst().isAfter(cutoff)) entries.removeFirst();
    }
}
