package com.da.extractor.service;


import com.da.extractor.entity.kb.KbMongo;
import com.da.extractor.pipeline.ExtractorService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class StreamingModeService {

    @Autowired
    ExtractorService extractorService;

    public void executeConfiguration(KbMongo config) throws Exception {

//        var isStreaming = config.getKbConfig().getScheduling().getTrainingConfig().getIsActive();
//
//        if(isStreaming){
//
//            var queryElastic = config.getKbConfig().getScheduling().getTrainingConfig().getQueryElastic();
//            var KbId = config.getKbConfig().getKbId();
//            var description = config.getKbConfig().getDescription();
//            var window = config.getKbConfig().getScheduling().getTrainingConfig().getWindow();
//            var ADAlgParameters = config.getKbConfig().getAdAlgParameters();
//
//            PipelineConfig pipelineConfig = new PipelineConfig(
//                    queryElastic,
//                    KbId,
//                    description,
//                    window,
//                    ConfigMode.TRAINING,
//                    ADAlgParameters
//            );
//
//            extractorService.extractData(pipelineConfig);
//
//
//        }
    }

}
