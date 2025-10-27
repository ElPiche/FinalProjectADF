package com.da.extractor.repository;

import com.da.extractor.entity.training.TrainConfig;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface TrainingConfigRepository extends MongoRepository<TrainConfig, String> {
}
