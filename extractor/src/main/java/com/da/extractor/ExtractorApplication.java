package com.da.extractor;

import com.da.extractor.repository.SeriesRepository;
import com.da.extractor.service.ElasticService;
import com.da.extractor.service.FilterService;
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
        SeriesRepository seriesRepository = context.getBean(SeriesRepository.class);
        FilterService filterService = context.getBean(FilterService.class);

        System.out.println("Extractor Service Started...");

        Map<String, Object> result = null;

        try {
            String clusterInfo = elasticService.getClusterInfo();
            System.out.println("Conexión exitosa a Elasticsearch:");
            System.out.println(clusterInfo);

            IO.println("Ejecutando consulta ESQL de ejemplo...");
            String exampleQuery = "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= \"2025-10-01T00:00:00.000Z\" AND @timestamp < \"2025-11-01T00:00:00.000Z\" | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS status_code_200_counter = COUNT() WHERE response == \"200\", status_code_5xx_counter = COUNT() WHERE response >= \"500\" AND response < \"600\" BY es_timestamp | SORT es_timestamp";
            result = elasticService.executeQuery(exampleQuery);

            IO.println("Resultados de la consulta:");
            result.forEach((key, value) -> System.out.println(key + ": " + value));

        } catch (Exception e) {
            System.err.println("Error con Elasticsearch: " + e.getMessage());
        }

        try {
            IO.println("Guardando resultados en MongoDB...");
            if (result != null) {
                seriesRepository.save(filterService.applyFilter(result));
//                seriesRepository.save(result);
                IO.println("Resultados guardados exitosamente en MongoDB.");
            } else {
                IO.println("No hay resultados para guardar en MongoDB.");
            }
        } catch (Exception e) {
            System.err.println("Error con MongoDB: " + e.getMessage());
        }

        IO.println("Extractor Service Finished.");

    }
}
