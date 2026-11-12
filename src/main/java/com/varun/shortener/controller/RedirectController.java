package com.varun.shortener.controller;

import com.varun.shortener.service.RedirectService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import java.net.URI;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.HttpRequestMethodNotSupportedException;

@RestController
public class RedirectController {
    private final RedirectService redirects;
    public RedirectController(RedirectService redirects) { this.redirects = redirects; }

    @Operation(summary = "Record one click and redirect to the original URL")
    @ApiResponse(responseCode = "302", description = "Found; Location contains the original URL")
    @ApiResponse(responseCode = "404", description = "Unknown or malformed short code")
    @ApiResponse(responseCode = "410", description = "Expired or disabled")
    @ApiResponse(responseCode = "503", description = "Database operation failed; no redirect issued")
    @GetMapping("/{code}")
    public ResponseEntity<Void> redirect(@PathVariable String code) {
        return ResponseEntity.status(HttpStatus.FOUND)
                .location(URI.create(redirects.redirect(code)))
                .cacheControl(CacheControl.noStore()).build();
    }

    @Operation(hidden = true)
    @RequestMapping(value = "/{code}", method = RequestMethod.HEAD)
    public void head() throws HttpRequestMethodNotSupportedException {
        // Spring otherwise invokes GET for HEAD, which would record a false click.
        throw new HttpRequestMethodNotSupportedException("HEAD", java.util.List.of("GET"));
    }
}
