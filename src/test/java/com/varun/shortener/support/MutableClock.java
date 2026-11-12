package com.varun.shortener.support;

import java.time.*;
import java.util.concurrent.atomic.AtomicReference;

public class MutableClock extends Clock {
    private final AtomicReference<Instant> now;
    public MutableClock(Instant initial) { now = new AtomicReference<>(initial); }
    public void set(Instant value) { now.set(value); }
    public void advance(Duration duration) { now.updateAndGet(value -> value.plus(duration)); }
    @Override public ZoneId getZone() { return ZoneOffset.UTC; }
    @Override public Clock withZone(ZoneId zone) { return Clock.fixed(instant(), zone); }
    @Override public Instant instant() { return now.get(); }
}
