package com.da.extractor.service;

import co.elastic.clients.util.DateTime;
import com.da.extractor.entity.kb.KbMongo;
import com.da.extractor.entity.serie.Mode;
import com.da.extractor.entity.training.TrainConfig;
import com.da.extractor.pipeline.DataPipelineFactory;
import com.da.extractor.pipeline.PipeMetadata;
import com.da.extractor.repository.anomaly_detection.TrainingConfigRepository;
import com.da.extractor.service.logging.PipeLineFlowLoggerFactory;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.List;

@Service
public class BatchModeService {

    private final DataPipelineFactory pipelineFactory;
    private final PipeLineFlowLoggerFactory pipeLineFlowLoggerFactory;

    private final TrainingConfigRepository trainingConfigRepository;

    public BatchModeService(DataPipelineFactory pipelineFactory, PipeLineFlowLoggerFactory pipeLineFlowLoggerFactory, TrainingConfigRepository trainingConfigRepository) {
        this.pipelineFactory = pipelineFactory;
        this.pipeLineFlowLoggerFactory = pipeLineFlowLoggerFactory;
        this.trainingConfigRepository = trainingConfigRepository;
    }

    public void executeConfiguration(KbMongo config) throws Exception {

        var kbTrainingConfig = config
                .getScheduling()
                .getTrainingConfig();

        if(kbTrainingConfig != null && kbTrainingConfig.getIsActive()){

            var logger = pipeLineFlowLoggerFactory.createLogger(config.getId());

            List<String> observedValues = config.getObservedValues();
            logger.info("Starting batch training for KB: " + config.getId() +
                    " with observed values: [" + String.join(",", observedValues) + "]");

            var pipeline = pipelineFactory.createPipeline(new PipeMetadata(
                    config.getId(),
                    observedValues,
                    Mode.TRAINING
            ));

            String query = kbTrainingConfig.getQueryElastic()
                    .replace("$from", kbTrainingConfig.getFrom())
                    .replace("$to", kbTrainingConfig.getTo());

            logger.info("Executing query: " + query);

            try{
                pipeline.process(query);
                var trainConfig = new TrainConfig(config);

                trainingConfigRepository.findByKbId(config.getId()).ifPresent(trainingConfig ->
                        trainConfig.setId(trainingConfig.getId()));
                trainingConfigRepository.save(trainConfig);

                logger.info("Batch training completed for KB: " + config.getId() + " at " + DateTime.of(Instant.now()));
            }catch (IllegalArgumentException e){
                logger.error(e.getMessage());
            }


        }

    }

}
