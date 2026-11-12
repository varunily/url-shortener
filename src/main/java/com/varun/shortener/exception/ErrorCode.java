package com.varun.shortener.exception;

import org.springframework.http.HttpStatus;

public enum ErrorCode {
    INVALID_REQUEST(HttpStatus.BAD_REQUEST, "The request is invalid."),
    URL_NOT_FOUND(HttpStatus.NOT_FOUND, "The short URL was not found."),
    URL_EXPIRED(HttpStatus.GONE, "The short URL has expired."),
    URL_DISABLED(HttpStatus.GONE, "The short URL has been disabled."),
    CODE_GENERATION_EXHAUSTED(HttpStatus.SERVICE_UNAVAILABLE, "Could not allocate a short code. Try again later."),
    RATE_LIMIT_EXCEEDED(HttpStatus.TOO_MANY_REQUESTS, "Creation limit of 100 requests per rolling hour exceeded."),
    RATE_LIMIT_CAPACITY(HttpStatus.SERVICE_UNAVAILABLE, "Creation is temporarily unavailable. Try again later."),
    DATABASE_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "The database operation could not be completed."),
    INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "An unexpected error occurred.");

    private final HttpStatus status;
    private final String detail;
    ErrorCode(HttpStatus status, String detail) { this.status = status; this.detail = detail; }
    public HttpStatus status() { return status; }
    public String detail() { return detail; }
}
