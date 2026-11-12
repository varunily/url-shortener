package com.varun.shortener.validation;

import static org.assertj.core.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.*;

class HttpUrlValidatorTest {
    private final HttpUrlValidator validator = new HttpUrlValidator();

    @ParameterizedTest
    @ValueSource(strings = {"https://example.com", "http://localhost:8080/a?x=1#section",
            "HTTPS://example.com/a%20b", "https://[::1]/", "https://xn--bcher-kva.example/path",
            "https://example.com/path?q=%E2%9C%93"})
    void acceptsAbsoluteHttpUrls(String input) { assertThat(validator.isValid(input, null)).isTrue(); }

    @ParameterizedTest
    @ValueSource(strings = {"", " ", "ftp://example.com", "javascript:alert(1)", "/relative",
            "//example.com", "https:///missing", "https://user:pass@example.com", "https://example.com:65536",
            "https://example.com:0", "https://example.com/%0d%0aInjected:value",
            "https://example.com/\r\nInjected:value", "https://example.com/a b",
            "https://example.com\\evil", "https://example.com/%xx", "https://"})
    void rejectsUnsafeOrMalformedUrls(String input) { assertThat(validator.isValid(input, null)).isFalse(); }

    @Test
    void rejectsOversizedUrl() { assertThat(validator.isValid("https://example.com/" + "a".repeat(2048), null)).isFalse(); }
}
