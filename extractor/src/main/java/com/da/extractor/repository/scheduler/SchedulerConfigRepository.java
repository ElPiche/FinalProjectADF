package com.da.extractor.repository.scheduler;

import com.da.extractor.entity.SchedulerConfig;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface SchedulerConfigRepository extends MongoRepository<SchedulerConfig, String> {
}
