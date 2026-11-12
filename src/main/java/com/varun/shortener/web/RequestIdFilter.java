package com.varun.shortener.web;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.UUID;
import org.slf4j.*;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {
    private static final Logger LOG = LoggerFactory.getLogger(RequestIdFilter.class);
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String id = UUID.randomUUID().toString();
        MDC.put("requestId", id);
        response.setHeader("X-Request-Id", id);
        long start = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            Object route = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
            LOG.atInfo().addKeyValue("method", request.getMethod())
                    .addKeyValue("route", route == null ? "unmatched" : route.toString())
                    .addKeyValue("status", response.getStatus())
                    .addKeyValue("durationMs", (System.nanoTime() - start) / 1_000_000)
                    .log("HTTP request completed");
            MDC.remove("requestId");
        }
    }
}
