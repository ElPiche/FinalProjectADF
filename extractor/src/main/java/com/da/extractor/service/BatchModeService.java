package com.da.extractor.service;

import com.da.extractor.dto.CreateMappingRequestDto;
import com.da.extractor.entity.kb.KbMongo;
import com.da.extractor.entity.serie.Mode;
import com.da.extractor.entity.training.TrainConfig;
import com.da.extractor.pipeline.DataPipelineFactory;
import com.da.extractor.pipeline.PipeMetadata;
import com.da.extractor.repository.anomaly_detection.TrainingConfigRepository;
import com.da.extractor.utils.Utils;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.temporal.ChronoUnit;
import java.util.regex.*;

import java.util.List;

@Service
public class BatchModeService {

    private final DataPipelineFactory pipelineFactory;

    private final TrainingConfigRepository trainingConfigRepository;

    private final HttpClient httpClient;

    private final Logger logger = LoggerFactory.getLogger(BatchModeService.class);

    @Value("${app.anomalies-insights.api.url}")
    private String anomalyModuleUrl;

    public BatchModeService(DataPipelineFactory pipelineFactory,
                            TrainingConfigRepository trainingConfigRepository,
                            HttpClient httpClient) {
        this.pipelineFactory = pipelineFactory;
        this.trainingConfigRepository = trainingConfigRepository;
        this.httpClient = httpClient;
    }

    public void executeConfiguration(KbMongo config) throws Exception {

        var kbTrainingConfig = config
                .getScheduling()
                .getTrainingConfig();

        if(kbTrainingConfig != null && kbTrainingConfig.getIsActive()){

            List<String> observedValues = config.getObservedValues();
            
            // Get timestamp field from query_mode, default to "timestamp" for backwards compatibility
            String timestampField = "timestamp";
            if (config.getQueryMode() != null && config.getQueryMode().getTimestampField() != null) {
                timestampField = config.getQueryMode().getTimestampField();
            }

            var pipeline = pipelineFactory.createPipeline(new PipeMetadata(
                    config.getId(),
                    observedValues,
                    Mode.TRAINING,
                    timestampField
            ));

            // Use unified elasticsearch_sql_query from root level, 
            // falling back to legacy training_query if available
            String baseQuery = config.getElasticsearchSqlQuery();
            if (baseQuery == null || baseQuery.isBlank()) {
                baseQuery = kbTrainingConfig.getQueryElastic();
            }
            
            if (baseQuery == null || baseQuery.isBlank()) {
                throw new IllegalStateException("No query found in config - need elasticsearch_sql_query or training_query");
            }
            
            String query = baseQuery
                    .replace("$from", kbTrainingConfig.getFrom())
                    .replace("$to", kbTrainingConfig.getTo());

                
            pipeline.process(query);
            var trainConfig = new TrainConfig(config);

            // Source index from KB config - used for both dashboard naming and anomaly output
            String sourceIndex = config.getSourceIndex();
            if (sourceIndex == null || sourceIndex.isBlank()) {
                throw new IllegalArgumentException("source_index is required in KB config");
            }

            // Enviar POST al módulo de anomalías - source index is used for everything
            CreateMappingRequestDto mappingRequest = new CreateMappingRequestDto(
                    config.getId(),
                    sourceIndex
            );
            String requestBody = new ObjectMapper().writeValueAsString(mappingRequest);

            try {
                logger.info("URL Módulo de Anomalías: {}", anomalyModuleUrl);
                logger.info("Enviando solicitud de creación de mapping con body: {}",
                         requestBody);

                HttpRequest request = HttpRequest.newBuilder()
                        .header("Accept", "application/json")
                        .uri(URI.create(anomalyModuleUrl + "/insights/dashboards"))
                        .header("Content-Type", "application/json")
                        .timeout(Duration.of(30, ChronoUnit.SECONDS))
                        .PUT(HttpRequest.BodyPublishers.ofString(requestBody))
                        .build();

                var response = httpClient.sendAsync(request, HttpResponse.BodyHandlers.ofString());

                response.thenAccept(res -> {
                    if(res.statusCode() == 200){
                        logger.info("Se ha creado el mapping para kbId \"{}\" source index \"{}\"", config.getId(), sourceIndex);

                    }else if(res.statusCode() == 500){
                        logger.error("Error interno del módulo de anomalías al crear el mapping para kbId \"{}\"\n: {}",
                                config.getId(), res.body());

                    }else if(res.statusCode() == 409) {
                        logger.error("Ya existe un mapping para el kbId \"{}\"\nServer Response:\n{}",
                                config.getId(), res.body());

                    }else {
                        logger.error("Error desconocido al crear el mapping para kbId \"{}\". Código: {}\nResponse:\n{}",
                                config.getId(), res.statusCode(), res.body());
                    }
                });
            }catch (Exception e){
                logger.error("Excepción al comunicarse con el módulo de anomalías para kbId \"{}\": {}",
                        config.getId(), e.getMessage(), e);
            }



            trainingConfigRepository.findByKbId(config.getId()).ifPresent(trainingConfig ->
                    trainConfig.setId(trainingConfig.getId()));
            trainingConfigRepository.save(trainConfig);

        }

    }
}
