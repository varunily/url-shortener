package com.varun.shortener.service;

import java.security.SecureRandom;
import org.springframework.stereotype.Component;

@Component
public class SecureRandomShortCodeGenerator implements ShortCodeGenerator {
    private static final char[] ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789".toCharArray();
    private final SecureRandom random = new SecureRandom();

    @Override
    public String generate() {
        char[] code = new char[7];
        for (int i = 0; i < code.length; i++) code[i] = ALPHABET[random.nextInt(ALPHABET.length)];
        return new String(code);
    }
}
