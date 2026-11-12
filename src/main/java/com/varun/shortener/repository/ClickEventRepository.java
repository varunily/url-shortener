package com.varun.shortener.repository;

import com.varun.shortener.analytics.ClickSummary;
import com.varun.shortener.analytics.DailyClickCount;
import com.varun.shortener.entity.ClickEvent;
import java.util.List;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

public interface ClickEventRepository extends JpaRepository<ClickEvent, Long> {
    @Query("""
            select new com.varun.shortener.analytics.ClickSummary(count(e), max(e.accessedAt))
            from ClickEvent e where e.url.id = :urlId
            """)
    ClickSummary summarize(@Param("urlId") long urlId);

    @Query(value = """
            SELECT (accessed_at AT TIME ZONE 'UTC')::date AS date, COUNT(*) AS clicks
            FROM click_events WHERE url_id = :urlId
            GROUP BY (accessed_at AT TIME ZONE 'UTC')::date ORDER BY date
            """, nativeQuery = true)
    List<DailyClickCount> dailyCounts(@Param("urlId") long urlId);
}
