package com.da.extractor.service;


import com.da.extractor.entity.kb.KbMongo;
import com.da.extractor.pipeline.ExtractorService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class StreamingModeService {

    @Autowired
    ExtractorService extractorService;

    private final SchedulerService schedulerService;

    public StreamingModeService(SchedulerService schedulerService) {
        this.schedulerService = schedulerService;
    }

    public void executeConfiguration(KbMongo config) throws Exception {

        var kbStreamingConfig = config
                .getScheduling()
                .getDetectionConfig();

        if(kbStreamingConfig != null){

            var queryElastic = kbStreamingConfig.getQueryElastic();
            var window = kbStreamingConfig.getWindow();
            var streamingConfigs = kbStreamingConfig.getFrequency();
            var id = config.getId();

            List<String> observedValues = config.getAdAlgParameters()
                    .getObservedValues();

            schedulerService.createStreamingTask(queryElastic,
                    window,
                    streamingConfigs,
                    id,
                    observedValues);
        }
    }


}
