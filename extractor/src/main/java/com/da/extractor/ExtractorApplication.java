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

        try {
            String clusterInfo = elasticService.getClusterInfo();
            System.out.println("Conexión exitosa a Elasticsearch:");
            System.out.println(clusterInfo);
        } catch (Exception e) {
            System.err.println("Error al conectar con Elasticsearch: " + e.getMessage());
        }

        System.out.println("Extractor Service Started...");
    }
}
