package com.da.extractor.config;

import com.da.extractor.repository.extractor.PipelineFlowLogEntryRepository;
import com.da.extractor.repository.extractor.SchedulerConfigRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
        basePackageClasses = {
                SchedulerConfigRepository.class,
                PipelineFlowLogEntryRepository.class
        },
        mongoTemplateRef = "schedulerMongoTemplate"
)
public class ExtractorRepoConfig {
}
