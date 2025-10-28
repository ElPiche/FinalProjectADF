package com.da.extractor.service;

import com.da.extractor.entity.kb.KbMongo;
import com.da.extractor.entity.serie.Mode;
import com.da.extractor.entity.training.TrainConfig;
import com.da.extractor.pipeline.DataPipelineFactory;
import com.da.extractor.pipeline.PipeMetadata;
import com.da.extractor.repository.TrainingConfigRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class BatchModeService {

    private final DataPipelineFactory pipelineFactory;

    private final TrainingConfigRepository trainingConfigRepository;

    public BatchModeService(DataPipelineFactory pipelineFactory, TrainingConfigRepository trainingConfigRepository) {
        this.pipelineFactory = pipelineFactory;
        this.trainingConfigRepository = trainingConfigRepository;
    }

    public void executeConfiguration(KbMongo config) throws Exception {

        var kbTrainingConfig = config
                .getScheduling()
                .getTrainingConfig();

        if(kbTrainingConfig != null){

            List<String> observedValues = config.getAdAlgParameters()
                    .getObservedValues();

            var pipeline = pipelineFactory.createPipeline(new PipeMetadata(
                    config.getId(),
                    observedValues,
                    Mode.TRAINING
            ));

            String query = kbTrainingConfig.getQueryElastic()
                    .replace("$from", kbTrainingConfig.getFrom())
                    .replace("$to", kbTrainingConfig.getTo());

            pipeline.process(query);

        }

    }

}
