package com.da.extractor;

import com.da.extractor.service.ElasticService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;


//@Slf4j
@SpringBootApplication
public class ExtractorApplication{

    public static void main(String[] args) {
        ApplicationContext context = SpringApplication.run(ExtractorApplication.class, args);

        ElasticService elasticService = context.getBean(ElasticService.class);

        System.out.println("Extractor Service Started...");

        try {
            String clusterInfo = elasticService.getClusterInfo();
            System.out.println("Conexión exitosa a Elasticsearch:");
            System.out.println(clusterInfo);

            IO.println("Ejecutando consulta ESQL de ejemplo...");
            String exampleQuery = "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= \"2025-10-01T00:00:00.000Z\" AND @timestamp < \"2025-11-01T00:00:00.000Z\" | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS cn_traffic = COUNT(*) WHERE geo.dest == \"CN\" BY es_timestamp | SORT es_timestamp";
            elasticService.executeQuery(exampleQuery);
        } catch (Exception e) {
            System.err.println("Error con Elasticsearch: " + e.getMessage());
        }

        IO.println("Extractor Service Finished.");

    }
}
