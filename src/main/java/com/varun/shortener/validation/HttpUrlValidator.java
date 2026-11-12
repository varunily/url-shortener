package com.varun.shortener.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.net.URI;
import java.net.URISyntaxException;
import java.util.regex.Pattern;

public class HttpUrlValidator implements ConstraintValidator<HttpUrl, String> {
    private static final Pattern ENCODED_CONTROL = Pattern.compile("%(?:0[0-9a-f]|1[0-9a-f]|7f)", Pattern.CASE_INSENSITIVE);

    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        if (value == null) return true; // @NotBlank owns presence validation.
        if (value.isBlank() || value.length() > 2048 || ENCODED_CONTROL.matcher(value).find()
                || value.codePoints().anyMatch(c -> Character.isISOControl(c) || Character.isWhitespace(c))) {
            return false;
        }
        try {
            URI uri = new URI(value).parseServerAuthority();
            return !uri.isOpaque() && uri.getHost() != null && uri.getUserInfo() == null
                    && (uri.getPort() == -1 || (uri.getPort() > 0 && uri.getPort() <= 65535))
                    && ("http".equalsIgnoreCase(uri.getScheme()) || "https".equalsIgnoreCase(uri.getScheme()));
        } catch (URISyntaxException ex) {
            return false;
        }
    }
}
