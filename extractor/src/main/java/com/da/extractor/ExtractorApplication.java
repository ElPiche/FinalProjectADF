package com.da.extractor;

import com.da.extractor.entity.KbMongo;
import com.da.extractor.repository.KbConfigRepository;
import com.da.extractor.service.ElasticService;
import com.da.extractor.service.KbConfigReaderService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;

import java.util.Map;


//@Slf4j
@SpringBootApplication
public class ExtractorApplication{

    public static void main(String[] args) {
        ApplicationContext context = SpringApplication.run(ExtractorApplication.class, args);

        ElasticService elasticService = context.getBean(ElasticService.class);

        KbConfigReaderService kbConfigReaderService = context.getBean(KbConfigReaderService.class);

        System.out.println("Extractor Service Started...");

        try {
            String clusterInfo = elasticService.getClusterInfo();
            System.out.println("Conexión exitosa a Elasticsearch:");
            System.out.println(clusterInfo);

            //IO.println("Ejecutando consulta ESQL de ejemplo...");
            //String exampleQuery = "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= \"2025-10-01T00:00:00.000Z\" AND @timestamp < \"2025-11-01T00:00:00.000Z\" | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS cn_traffic = COUNT(*) WHERE geo.dest == \"CN\" BY es_timestamp | SORT es_timestamp";
            //Map<String, Object> result = elasticService.executeQuery(exampleQuery);

            //IO.println("Resultados de la consulta:");
            //result.forEach((key, value) -> System.out.println(key + ": " + value));

            //String statusCodesQuery = "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= $from  AND @timestamp <=  $to | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS status_code_200_counter = COUNT(*) WHERE response == \"200\", status_code_5xx_counter = COUNT(*) WHERE response >= \"500\" AND response < \"600\" BY es_timestamp | SORT es_timestamp";

            // Query desde mongo.
            /*
            KbMongo doc = kbConfigReaderService.getByKbId("1fbb07a4-favf-46ed-9eae-b8d1289c570c");

            IO.print("Documento");

            KbMongo.KbConfig cfg = doc.getKbConfig();

            System.out.println("KB: " + cfg.getKbId() + " - " + cfg.getDescription());

            String rawQuery = cfg.getQueryElastic();

            IO.println("QUERY DE KB RAW: " + rawQuery);

            var tr = cfg.getScheduling().getTrainingConfig();

            String q = rawQuery
                    .replace("$from", "\"" + tr.getFrom() + "\"")
                    .replace("$to",   "\"" + tr.getTo()   + "\"");

            IO.println("QUERY DE TRAINING REPLACE: " + q);

            Map<String, Object> result = elasticService.executeQuery(q);

            IO.println("ejecutando query desde config mongo.");

            elasticService.printEsqlResult(result);*/

            //TODO: Hacer un servicio que se encargue de ejecutar esto
            var configs = kbConfigReaderService.listAll();

            for(KbMongo kbMongoConfig : configs){

                var config = kbMongoConfig.getKbConfig();

                if(config == null){
                    IO.println("Saltando documento, estructura invalida");
                    continue;
                }

                IO.println("\n=== KB ===");
                IO.println("Id mongo: " + kbMongoConfig.getId());
                IO.println("Descripción: " + config.getDescription());
                IO.println("Kb id: " + config.getKbId());

                if (config.getQueryElastic() == null) {
                    System.out.println("Sin query elastic skipeo iteración");
                    continue;
                }

                if (config.getScheduling() == null || config.getScheduling().getTrainingConfig() == null) {
                    System.out.println("Sin scheduling/trainingConfig; salto.");
                    continue;
                }

                var tr = config.getScheduling().getTrainingConfig();

                if (tr.getFrom() == null || tr.getTo() == null) {
                    System.out.println("TrainingConfig sin from/to; salto.");
                    continue;
                }

                String q = config.getQueryElastic()
                        .replace("$from", "\"" + tr.getFrom() + "\"")
                        .replace("$to",   "\"" + tr.getTo()   + "\"");

                System.out.println("ESQL => " + q);

                try {
                    var result = elasticService.executeQuery(q);
                    elasticService.printEsqlResult(result);
                } catch (Exception ex) {
                    System.err.println("Error ejecutando ESQL para KB " + config.getKbId() + ": " + ex.getMessage());
                }

            }

        } catch (Exception e) {
            System.err.println("Error con Elasticsearch: " + e.getMessage());
        }

        IO.println("Extractor Service Finished.");
    }
}
