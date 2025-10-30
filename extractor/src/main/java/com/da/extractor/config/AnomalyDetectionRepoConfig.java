package com.da.extractor.config;

import com.da.extractor.repository.anomaly_detection.SeriesRepository;
import com.da.extractor.repository.anomaly_detection.TrainingConfigRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
        basePackageClasses = {
                SeriesRepository.class,
                TrainingConfigRepository.class
        },
        mongoTemplateRef = "anomalyDetectionMongoTemplate"
)
public class AnomalyDetectionRepoConfig {
}
