package com.da.extractor.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@Configuration
public class ChangeStreamInfraConfig {

    @Bean
    public ExecutorService changeStreamExecutor() {
        return Executors.newFixedThreadPool(1);
    }

}
