package com.varun.shortener.exception;

import java.net.URI;
import java.time.Clock;
import org.slf4j.MDC;
import org.springframework.http.*;
import org.springframework.stereotype.Component;

@Component
public class ApiProblemFactory {
    private final Clock clock;
    public ApiProblemFactory(Clock clock) { this.clock = clock; }

    public ProblemDetail create(ErrorCode code) {
        return create(code.status(), code.name(), code.detail());
    }

    public ProblemDetail create(HttpStatusCode status, String code, String detail) {
        var problem = ProblemDetail.forStatusAndDetail(status, detail);
        problem.setType(URI.create("urn:url-shortener:error:" + code.toLowerCase(java.util.Locale.ROOT).replace('_', '-')));
        problem.setProperty("code", code);
        problem.setProperty("requestId", MDC.get("requestId"));
        problem.setProperty("timestamp", clock.instant());
        return problem;
    }
}
