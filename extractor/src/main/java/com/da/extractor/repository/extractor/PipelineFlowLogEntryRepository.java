package com.da.extractor.repository.extractor;

import com.da.extractor.entity.logs.pipeline.PipelineFlowLogEntry;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface PipelineFlowLogEntryRepository extends MongoRepository<PipelineFlowLogEntry, String> {
}
