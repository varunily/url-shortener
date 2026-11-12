package com.varun.shortener.analytics;

import java.time.LocalDate;

public interface DailyClickCount {
    LocalDate getDate();
    long getClicks();
}
