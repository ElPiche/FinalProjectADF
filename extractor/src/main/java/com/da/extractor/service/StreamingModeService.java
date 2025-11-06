package com.da.extractor.service;


import com.da.extractor.entity.SchedulerConfig;
import com.da.extractor.entity.kb.KbMongo;
import com.da.extractor.entity.serie.Mode;
import com.da.extractor.pipeline.ExtractorService;
import com.da.extractor.pipeline.PipeMetadata;
import com.da.extractor.repository.extractor.SchedulerConfigRepository;
import com.da.extractor.service.logging.PipeLineFlowLoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.Date;
import java.util.List;

@Service
public class StreamingModeService {

    @Autowired
    ExtractorService extractorService;

    private final SchedulerConfigRepository schedulerConfigRepository;
    private final PipeLineFlowLoggerFactory pipeLineFlowLoggerFactory;

    private final SchedulerService schedulerService;

    public StreamingModeService(SchedulerConfigRepository schedulerConfigRepository,
                                PipeLineFlowLoggerFactory pipeLineFlowLoggerFactory,
                                SchedulerService schedulerService) {
        this.schedulerConfigRepository = schedulerConfigRepository;
        this.pipeLineFlowLoggerFactory = pipeLineFlowLoggerFactory;
        this.schedulerService = schedulerService;
    }

    public void executeConfiguration(KbMongo config) throws Exception {

        var kbStreamingConfig = config
                .getScheduling()
                .getDetectionConfig();

        if(kbStreamingConfig != null && kbStreamingConfig.isActive()) {
            var queryElastic = kbStreamingConfig.getQueryElastic();
            var window = kbStreamingConfig.getWindow();
            var streamingConfigs = kbStreamingConfig.getFrequency();
            var startAt = kbStreamingConfig.getStart();
            var id = config.getId();

            List<String> observedValues = config.getObservedValues();

            SchedulerConfig schedulerConfig = new SchedulerConfig(
                    null,
                    id,
                    window,
                    streamingConfigs,
                    queryElastic,
                    startAt,
                    new Date()
            );

            PipeMetadata pipeMetadata = new PipeMetadata(
                    id,
                    observedValues,
                    Mode.DETECTION
            );

            schedulerConfigRepository.findByKbId(id).ifPresent(existingConfig -> {
                schedulerConfig.setId(existingConfig.getId());
            });

            schedulerService.createStreamingTask(
                    schedulerConfigRepository.save(schedulerConfig),
                    pipeMetadata
            );
        }
    }


}
