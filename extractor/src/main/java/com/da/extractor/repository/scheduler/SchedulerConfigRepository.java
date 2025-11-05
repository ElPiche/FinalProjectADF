package com.da.extractor.repository.scheduler;

import com.da.extractor.entity.SchedulerConfig;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.Optional;

public interface SchedulerConfigRepository extends MongoRepository<SchedulerConfig, String> {
    Optional<SchedulerConfig> findByKbId(String kbId);
}
