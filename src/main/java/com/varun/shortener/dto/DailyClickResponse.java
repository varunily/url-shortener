package com.varun.shortener.dto;

import java.time.LocalDate;

public record DailyClickResponse(LocalDate date, long clicks) {}
