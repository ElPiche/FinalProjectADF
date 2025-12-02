package com.da.extractor.service;


import com.da.extractor.entity.SchedulerConfig;
import com.da.extractor.entity.kb.KbMongo;
import com.da.extractor.entity.serie.Mode;
import com.da.extractor.pipeline.PipeMetadata;
import com.da.extractor.repository.scheduler.SchedulerConfigRepository;
import com.da.extractor.utils.Utils;
import org.springframework.stereotype.Service;

import java.util.Date;
import java.util.List;

@Service
public class StreamingModeService {

    private final SchedulerConfigRepository schedulerConfigRepository;

    private final SchedulerService schedulerService;

    public StreamingModeService(SchedulerConfigRepository schedulerConfigRepository,
                                SchedulerService schedulerService) {
        this.schedulerConfigRepository = schedulerConfigRepository;
        this.schedulerService = schedulerService;
    }

    public void executeConfiguration(KbMongo config) {

        var kbStreamingConfig = config
                .getScheduling()
                .getDetectionConfig();

        if(kbStreamingConfig != null && kbStreamingConfig.isActive()) {

            // Use unified elasticsearch_sql_query from root level, 
            // falling back to legacy detection_query if available
            String queryElastic = config.getElasticsearchSqlQuery();
            if (queryElastic == null || queryElastic.isBlank()) {
                queryElastic = kbStreamingConfig.getQueryElastic();
            }
            
            var window = kbStreamingConfig.getWindow();
            var creationDate = new Date();
            var seconds = creationDate
                    .toInstant()
                    .atZone(java.time.ZoneId.systemDefault())
                    .toLocalTime()
                    .getSecond();
            var frequency = Utils.normalizeCron(kbStreamingConfig.getFrequency(), seconds);
            var startAt = kbStreamingConfig.getStart();
            var id = config.getId();

            List<String> observedValues = config.getObservedValues();
            
            // Get timestamp field from query_mode, default to "timestamp" for backwards compatibility
            String timestampField = "timestamp";
            if (config.getQueryMode() != null && config.getQueryMode().getTimestampField() != null) {
                timestampField = config.getQueryMode().getTimestampField();
            }

            SchedulerConfig schedulerConfig = new SchedulerConfig(
                    null,
                    id,
                    window,
                    frequency,
                    queryElastic,
                    startAt,
                    new Date()
            );

            PipeMetadata pipeMetadata = new PipeMetadata(
                    id,
                    observedValues,
                    Mode.DETECTION,
                    timestampField
            );

            schedulerConfigRepository.findByKbId(id).ifPresent(existingConfig ->
                    schedulerConfig.setId(existingConfig.getId()));

            schedulerService.createStreamingTask(
                    schedulerConfigRepository.save(schedulerConfig),
                    pipeMetadata
            );
        }
    }


}
