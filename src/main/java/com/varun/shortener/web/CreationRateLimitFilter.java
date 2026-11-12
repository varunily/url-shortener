package com.varun.shortener.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.varun.shortener.exception.*;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.UrlPathHelper;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
public class CreationRateLimitFilter extends OncePerRequestFilter {
    private final InMemoryRateLimiter limiter;
    private final ApiProblemFactory problems;
    private final ObjectMapper mapper;

    public CreationRateLimitFilter(InMemoryRateLimiter limiter, ApiProblemFactory problems, ObjectMapper mapper) {
        this.limiter = limiter; this.problems = problems; this.mapper = mapper;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        // Match Spring MVC's decoded path without matrix parameters to prevent quota bypasses.
        String path = UrlPathHelper.defaultInstance.getPathWithinApplication(request);
        return !"POST".equals(request.getMethod()) || !"/api/v1/urls".equals(path);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        var decision = limiter.acquire(request.getRemoteAddr());
        if (decision.allowed()) {
            chain.doFilter(request, response);
            return;
        }
        var code = decision.atCapacity() ? ErrorCode.RATE_LIMIT_CAPACITY : ErrorCode.RATE_LIMIT_EXCEEDED;
        response.setStatus(code.status().value());
        response.setHeader("Retry-After", Long.toString(decision.retryAfterSeconds()));
        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        mapper.writeValue(response.getOutputStream(), problems.create(code));
    }
}
