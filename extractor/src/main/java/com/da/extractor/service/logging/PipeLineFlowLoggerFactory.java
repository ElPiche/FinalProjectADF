package com.da.extractor.service.logging;

import com.da.extractor.repository.extractor.PipelineFlowLogEntryRepository;
import org.springframework.stereotype.Component;

@Component
public class PipeLineFlowLoggerFactory {

    private final PipelineFlowLogEntryRepository repository;

    public PipeLineFlowLoggerFactory(PipelineFlowLogEntryRepository repository) {
        this.repository = repository;
    }

    public PipelineFlowLogger createLogger(String kbId) {
        return new PipelineFlowLogger(repository, kbId);
    }
}
