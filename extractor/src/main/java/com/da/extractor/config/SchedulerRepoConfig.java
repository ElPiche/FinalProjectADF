package com.da.extractor.config;

import com.da.extractor.repository.scheduler.SchedulerConfigRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
        basePackageClasses = {
                SchedulerConfigRepository.class
        },
        mongoTemplateRef = "schedulerMongoTemplate"
)
public class SchedulerRepoConfig {
}
