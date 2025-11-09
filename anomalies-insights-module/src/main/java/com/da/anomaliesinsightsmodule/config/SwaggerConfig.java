package com.da.anomaliesinsightsmodule.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SwaggerConfig {

    @Bean
    public OpenAPI getOpenAPI() {
        return new OpenAPI().info(getApiInfo());
    }

    private Info getApiInfo(){
     return new Info().title("Anomalies insights module");
    }
}
