package com.varun.shortener.configuration;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfiguration {
    @Bean
    OpenAPI shortenerOpenApi(ShortenerProperties properties) {
        return new OpenAPI().info(new Info().title("URL Shortener API").version("v1")
                .description("Phase 1: public link management, redirects and UTC click analytics."))
                .addServersItem(new Server().url(properties.baseUrl()));
    }
}
