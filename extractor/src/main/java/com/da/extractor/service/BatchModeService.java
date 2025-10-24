package com.da.extractor.service;

import com.da.extractor.entity.KbMongo;
import com.da.extractor.enums.ConfigMode;
import com.da.extractor.model.PipelineConfig;
import com.da.extractor.service.pipeline.ExtractorService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.Locale;

@Service
public class BatchModeService {

    @Autowired
    ExtractorService extractorService;

    public void executeConfiguration(KbMongo config) throws Exception {

        var isBatch = config.getKbConfig().getScheduling().getTrainingConfig().getIsActive();

        if(isBatch){

            var queryElastic = config.getKbConfig().getScheduling().getTrainingConfig().getQueryElastic();
            var KbId = config.getKbConfig().getKbId();
            var description = config.getKbConfig().getDescription();
            var window = config.getKbConfig().getScheduling().getTrainingConfig().getWindow();
            var ADAlgParameters = config.getKbConfig().getAdAlgParameters();

            PipelineConfig pipelineConfig = new PipelineConfig(
                    queryElastic,
                    KbId,
                    description,
                    window,
                    ConfigMode.TRAINING,
                    ADAlgParameters
            );

//            extractorService.extractData(pipelineConfig);


        }

    }

}
