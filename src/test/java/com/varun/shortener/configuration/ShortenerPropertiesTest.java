package com.varun.shortener.configuration;

import static org.assertj.core.api.Assertions.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class ShortenerPropertiesTest {
    @ParameterizedTest
    @ValueSource(strings = {"http://localhost:8080/path", "https://user:password@example.com",
            "javascript:alert(1)", "http://example.com?x=1", "http://example.com#fragment",
            "http://example.com:99999", "http://example.com:0"})
    void rejectsInvalidPublicOrigins(String value) {
        assertThatThrownBy(() -> new ShortenerProperties(value)).isInstanceOf(IllegalArgumentException.class);
    }
}
