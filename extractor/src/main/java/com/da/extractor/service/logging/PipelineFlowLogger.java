package com.da.extractor.service.logging;

import com.da.extractor.entity.logs.pipeline.PipelineFlowLogEntry;
import com.da.extractor.repository.extractor.PipelineFlowLogEntryRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.logging.LogLevel;
import org.springframework.stereotype.Service;

public class PipelineFlowLogger {
    private final PipelineFlowLogEntryRepository repository;
    private final String kbId;

    private static final Logger log = LoggerFactory.getLogger(PipelineFlowLogger.class);


    public PipelineFlowLogger(PipelineFlowLogEntryRepository repository, String kbId) {
        this.repository = repository;
        this.kbId = kbId;
    }

    public void info(String message) {
        var logEntry = createLogEntry(LogLevel.INFO, message);

        repository.save(logEntry);
        log.info(logEntry.toString());
    }

    public void warn(String message) {
        var logEntry = createLogEntry(LogLevel.WARN, message);

        repository.save(logEntry);
        log.warn(logEntry.toString());
    }

    public void error(String message) {
        var logEntry = createLogEntry(LogLevel.ERROR, message);

        repository.save(logEntry);
        log.error(logEntry.toString());
    }

    private PipelineFlowLogEntry createLogEntry(LogLevel level, String message) {
        var logEntry = new PipelineFlowLogEntry();
        logEntry.setKbId(kbId);
        logEntry.setLogLevel(level);
        logEntry.setMessage(message);

        return logEntry;
    }
}
