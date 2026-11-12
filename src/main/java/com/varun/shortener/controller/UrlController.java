package com.varun.shortener.controller;

import com.varun.shortener.analytics.AnalyticsService;
import com.varun.shortener.dto.*;
import com.varun.shortener.service.UrlService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/urls")
public class UrlController {
    private final UrlService urls;
    private final AnalyticsService analytics;
    public UrlController(UrlService urls, AnalyticsService analytics) {
        this.urls = urls; this.analytics = analytics;
    }

    @Operation(summary = "Create a short URL", description = "100 POST requests per rolling hour per connection IP.")
    @ApiResponse(responseCode = "201", description = "Created")
    @ApiResponse(responseCode = "400", description = "Invalid HTTP(S) URL or expiration")
    @ApiResponse(responseCode = "429", description = "Rate limit exceeded; Retry-After indicates seconds")
    @ApiResponse(responseCode = "503", description = "Database or code allocation unavailable")
    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<UrlResponse> create(@Valid @RequestBody CreateUrlRequest request) {
        var response = urls.create(request);
        return ResponseEntity.created(URI.create("/api/v1/urls/" + response.shortCode())).body(response);
    }

    @Operation(summary = "Read link metadata, including expired or disabled links")
    @ApiResponse(responseCode = "404", description = "Unknown or malformed short code")
    @GetMapping("/{code}")
    public UrlResponse get(@PathVariable String code) { return urls.get(code); }

    @Operation(summary = "Read lifetime click totals and daily UTC counts")
    @ApiResponse(responseCode = "404", description = "Unknown or malformed short code")
    @GetMapping("/{code}/stats")
    public UrlStatsResponse stats(@PathVariable String code) { return analytics.stats(code); }

    @Operation(summary = "Disable a link permanently", description = "Idempotent; metadata and stats remain available.")
    @ApiResponse(responseCode = "404", description = "Unknown or malformed short code")
    @PatchMapping("/{code}/disable")
    public UrlResponse disable(@PathVariable String code) { return urls.disable(code); }
}
