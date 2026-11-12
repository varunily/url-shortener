package com.varun.shortener.service;

import com.varun.shortener.entity.*;
import com.varun.shortener.exception.*;
import com.varun.shortener.repository.*;
import java.time.Clock;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RedirectService {
    private final UrlRepository urls;
    private final ClickEventRepository clicks;
    private final Clock clock;

    public RedirectService(UrlRepository urls, ClickEventRepository clicks, Clock clock) {
        this.urls = urls; this.clicks = clicks; this.clock = clock;
    }

    @Transactional(timeout = 5)
    public String redirect(String code) {
        UrlService.validateCode(code);
        var url = urls.findForRedirect(code).orElseThrow(() -> new ApiException(ErrorCode.URL_NOT_FOUND));
        var now = clock.instant(); // Check after acquiring the lock.
        switch (url.statusAt(now)) {
            case DISABLED -> throw new ApiException(ErrorCode.URL_DISABLED);
            case EXPIRED -> throw new ApiException(ErrorCode.URL_EXPIRED);
            case ACTIVE -> { }
        }
        clicks.save(new ClickEvent(url, now));
        // Spring commits this transaction before the controller constructs the 302 response.
        return url.getOriginalUrl();
    }
}
