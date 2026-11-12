package com.varun.shortener.service;

import static org.assertj.core.api.Assertions.*;
import java.util.HashSet;
import org.junit.jupiter.api.Test;

class SecureRandomShortCodeGeneratorTest {
    @Test
    void generatesSevenBase62CharactersWithVariety() {
        var generator = new SecureRandomShortCodeGenerator();
        var values = new HashSet<String>();
        for (int i = 0; i < 1000; i++) {
            String code = generator.generate();
            assertThat(code).matches("[A-Za-z0-9]{7}");
            values.add(code);
        }
        // Randomness does not prove uniqueness; PostgreSQL enforces that separately.
        assertThat(values.size()).isGreaterThan(990);
    }
}
