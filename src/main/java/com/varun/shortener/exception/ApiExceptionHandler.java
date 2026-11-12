package com.varun.shortener.exception;

import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.http.*;
import org.springframework.lang.Nullable;
import org.springframework.transaction.TransactionException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {
    private static final Logger LOG = LoggerFactory.getLogger(ApiExceptionHandler.class);
    private final ApiProblemFactory problems;
    public ApiExceptionHandler(ApiProblemFactory problems) { this.problems = problems; }

    @ExceptionHandler(ApiException.class)
    ResponseEntity<Object> business(ApiException ex) {
        return response(ex.code());
    }

    @ExceptionHandler({DataAccessException.class, TransactionException.class})
    ResponseEntity<Object> database(RuntimeException ex) {
        LOG.atError().addKeyValue("errorType", ex.getClass().getSimpleName()).log("Database operation failed");
        return response(ErrorCode.DATABASE_UNAVAILABLE);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<Object> unexpected(Exception ex) {
        LOG.atError().addKeyValue("errorType", ex.getClass().getSimpleName()).log("Unhandled request failure");
        return response(ErrorCode.INTERNAL_ERROR);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(MethodArgumentNotValidException ex,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        var problem = problems.create(ErrorCode.INVALID_REQUEST);
        problem.setProperty("errors", ex.getBindingResult().getFieldErrors().stream()
                .map(e -> Map.of("field", e.getField(), "message",
                        e.getDefaultMessage() == null ? "invalid value" : e.getDefaultMessage()))
                .distinct().toList());
        return ResponseEntity.status(status).contentType(MediaType.APPLICATION_PROBLEM_JSON).body(problem);
    }

    @Override
    protected ResponseEntity<Object> handleExceptionInternal(Exception ex, @Nullable Object body,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        HttpStatus known = HttpStatus.resolve(status.value());
        var problem = problems.create(status, "HTTP_" + status.value(),
                known == null ? "Request could not be processed." : known.getReasonPhrase());
        var safeHeaders = new HttpHeaders();
        safeHeaders.putAll(headers);
        safeHeaders.setContentType(MediaType.APPLICATION_PROBLEM_JSON);
        return new ResponseEntity<>(problem, safeHeaders, status);
    }

    private ResponseEntity<Object> response(ErrorCode code) {
        return ResponseEntity.status(code.status()).contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problems.create(code));
    }
}
