package com.varun.shortener.configuration;

import java.time.Clock;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
@EnableConfigurationProperties(ShortenerProperties.class)
public class ApplicationConfiguration {
    @Bean
    Clock clock() { return Clock.systemUTC(); }
}
