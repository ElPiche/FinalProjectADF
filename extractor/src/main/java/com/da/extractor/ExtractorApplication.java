package com.da.extractor;

import com.da.extractor.entity.serie.Mode;
import com.da.extractor.pipeline.*;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;

import java.util.List;


//@Slf4j
@SpringBootApplication
public class ExtractorApplication{

    public static void main(String[] args) throws Exception {
        ApplicationContext context = SpringApplication.run(ExtractorApplication.class, args);

        DataPipelineFactory pipelineFactory = context.getBean(DataPipelineFactory.class);


        //Esto ejecuta el kbconfig, haciendo entrar a ejecución el flujo entero.
//        kbConfigReaderService.getAllConfigs();

        System.out.println("Extractor Service Started...");

//        Map<String, Object> result = null;

        try {

            var pipeline = pipelineFactory.createPipeline(
                    new PipeMetadata(
                            "1fbb07a4-favf-46ed-9eae-b8d1289c570c",
                            List.of("status_code_5xx_counter"),
                            Mode.TRAINING
                    )
            );

            pipeline.process("SELECT DATE_TRUNC('HOUR', \"@timestamp\") " +
                    "AS es_timestamp, SUM(CASE WHEN CAST(response AS INTEGER) >= 500 AND CAST(response AS INTEGER) " +
                    "< 600 THEN 1 ELSE 0 END) AS status_code_5xx_counter FROM \".ds-kibana_sample_data_logs-*\"" +
                    " WHERE \"@timestamp\" >= '2025-10-01T00:00:00.000Z' AND \"@timestamp\" < '2025-11-01T00:00:00.000Z' " +
                    "GROUP BY es_timestamp ORDER BY es_timestamp");


//            extractorService.extractData("SELECT DATE_TRUNC('HOUR', \"@timestamp\") " +
//                    "AS es_timestamp, SUM(CASE WHEN CAST(response AS INTEGER) >= 500 AND CAST(response AS INTEGER) " +
//                    "< 600 THEN 1 ELSE 0 END) AS status_code_5xx_counter FROM \".ds-kibana_sample_data_logs-*\"" +
//                    " WHERE \"@timestamp\" >= '2025-10-01T00:00:00.000Z' AND \"@timestamp\" < '2025-11-01T00:00:00.000Z' " +
//                    "GROUP BY es_timestamp ORDER BY es_timestamp");
//
//            loaderService.loadTrainingConfig(new TrainConfig(
//                    null,
//                    "1fbb07a4-favf-46ed-9eae-b8d1289c570c",
//                    "Training config example",
//                    Date.from(Instant.now()),
//                    (short) 0,
//                    new AlgorithmConfig(
//                            "zscore",
//                            new AlgorithmParameters(
//                                    60,
//                                    List.of("status_code_5xx_counter"),
//                                    Date.from(Instant.parse("2025-10-01T00:00:00.000Z")),
//                                    Date.from(Instant.parse("2025-11-01T00:00:00.000Z"))
//                            )
//                    )
//
//            ));

        } catch (Exception e) {
            System.err.println("Error al correr el prgorama: " + e.getMessage());
        }

        IO.println("Extractor Service Finished.");

    }
}
