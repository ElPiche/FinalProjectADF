package com.da.extractor;

import com.da.extractor.entity.KbMongo;
import com.da.extractor.service.ElasticService;
import com.da.extractor.service.KbConfigReaderService;
import com.da.extractor.repository.SeriesRepository;
import com.da.extractor.service.pipeline.ExtractorService;
import com.da.extractor.service.pipeline.FilterService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;

import java.io.IOException;
import java.util.Map;


//@Slf4j
@SpringBootApplication
public class ExtractorApplication{

    public static void main(String[] args) throws Exception {
        ApplicationContext context = SpringApplication.run(ExtractorApplication.class, args);

        ElasticService elasticService = context.getBean(ElasticService.class);
        SeriesRepository seriesRepository = context.getBean(SeriesRepository.class);
        FilterService filterService = context.getBean(FilterService.class);
        ExtractorService extractorService = context.getBean(ExtractorService.class);

        KbConfigReaderService kbConfigReaderService = context.getBean(KbConfigReaderService.class);


        //Esto ejecuta el kbconfig, haciendo entrar a ejecución el flujo entero.
//        kbConfigReaderService.getAllConfigs();

        System.out.println("Extractor Service Started...");

//        Map<String, Object> result = null;

        try {
//            String clusterInfo = elasticService.getClusterInfo();
//            System.out.println("Conexión exitosa a Elasticsearch:");
//            System.out.println(clusterInfo);

            /*
            IO.println("Ejecutando consulta ESQL de ejemplo...");
            String exampleQuery = "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= \"2025-10-01T00:00:00.000Z\" AND @timestamp < \"2025-11-01T00:00:00.000Z\" | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS status_code_200_counter = COUNT() WHERE response == \"200\", status_code_5xx_counter = COUNT() WHERE response >= \"500\" AND response < \"600\" BY es_timestamp | SORT es_timestamp";
            result = elasticService.executeQuery(exampleQuery);
            */

            //String statusCodesQuery = "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= $from  AND @timestamp <=  $to | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS status_code_200_counter = COUNT(*) WHERE response == \"200\", status_code_5xx_counter = COUNT(*) WHERE response >= \"500\" AND response < \"600\" BY es_timestamp | SORT es_timestamp";

            //TODO: Flujo para modo de entrenamiento
            //Obtener la configuración.
            //Consultar id de KB en mongoDB de series. Si existe


            //TODO: Hacer un servicio que se encargue de ejecutar esto
//            var configs = kbConfigReaderService.listAll();
//
//            for(KbMongo kbMongoConfig : configs){
//
//                var config = kbMongoConfig.getKbConfig();
//
//                if(config == null){
//                    IO.println("Saltando documento, estructura invalida");
//                    continue;
//                }
//
//                IO.println("\n=== KB ===");
//                IO.println("Id mongo: " + kbMongoConfig.getId());
//                IO.println("Descripción: " + config.getDescription());
//                IO.println("Kb id: " + config.getKbId());

//                if (config.getQueryElastic() == null) {
//                    System.out.println("Sin query elastic skipeo iteración");
//                    continue;
//                }
//
//                if (config.getScheduling() == null || config.getScheduling().getTrainingConfig() == null) {
//                    System.out.println("Sin scheduling/trainingConfig; salto.");
//                    continue;
//                }
//
//                var tr = config.getScheduling().getTrainingConfig();
//
//                if (tr.getFrom() == null || tr.getTo() == null) {
//                    System.out.println("TrainingConfig sin from/to; salto.");
//                    continue;
//                }
//
//                String q = config.getQueryElastic()
//                        .replace("$from", "\"" + tr.getFrom() + "\"")
//                        .replace("$to",   "\"" + tr.getTo()   + "\"");
//
//                System.out.println("ESQL => " + q);
//
//                try {
//                    result = elasticService.executeQuery(q);
//
//                    //elasticService.printEsqlResult(result);
//
//                    if (result != null) {
//                        seriesRepository.save(filterService.applyFilter(result, config.getKbId(), config.getDescription()));
//                        IO.println("Resultados guardados exitosamente en MongoDB.");
//                    } else {
//                        IO.println("No hay resultados para guardar en MongoDB.");
//                    }
//
//                } catch (Exception ex) {
//                    System.err.println("Error ejecutando ESQL para KB " + config.getKbId() + ": " + ex.getMessage());
//                }


//            }

            extractorService.extractData("SELECT DATE_TRUNC('HOUR', \"@timestamp\") AS es_timestamp, " +
                    "SUM(CASE WHEN response = '200' THEN 1 ELSE 0 END) AS status_code_200_counter, SUM(CASE WHEN " +
                    "CAST(response AS INTEGER) >= 500 AND CAST(response AS INTEGER) < 600 THEN 1 ELSE 0 END) AS " +
                    "status_code_5xx_counter FROM \".ds-kibana_sample_data_logs-*\" WHERE \"@timestamp\" >= " +
                    "'2025-10-01T00:00:00.000Z' AND \"@timestamp\" < '2025-11-01T00:00:00.000Z' GROUP BY " +
                    "es_timestamp ORDER BY es_timestamp");

        } catch (Exception e) {
            System.err.println("Error con Elasticsearch: " + e.getMessage());
        }

        IO.println("Extractor Service Finished.");

    }
}
