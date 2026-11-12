package com.varun.shortener.repository;

import com.varun.shortener.entity.ShortUrl;
import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.Optional;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

public interface UrlRepository extends JpaRepository<ShortUrl, Long> {
    Optional<ShortUrl> findByShortCode(String shortCode);

    @Modifying
    @Query(value = """
            INSERT INTO urls (short_code, original_url, created_at, expires_at, disabled)
            VALUES (:code, :original, :created, :expires, false)
            ON CONFLICT (short_code) DO NOTHING
            """, nativeQuery = true)
    int insertIfAvailable(@Param("code") String code, @Param("original") String original,
                          @Param("created") Instant created, @Param("expires") Instant expires);

    @Lock(LockModeType.PESSIMISTIC_READ)
    @Query("select u from ShortUrl u where u.shortCode = :code")
    Optional<ShortUrl> findForRedirect(@Param("code") String code);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select u from ShortUrl u where u.shortCode = :code")
    Optional<ShortUrl> findForDisable(@Param("code") String code);
}
