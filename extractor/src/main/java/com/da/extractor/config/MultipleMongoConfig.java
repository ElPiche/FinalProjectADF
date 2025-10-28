package com.da.extractor.config;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.data.mongodb.core.MongoTemplate;

@Configuration
public class MultipleMongoConfig {

    @Value("${spring.data.mongodb.uri}")
    private String uri;

    @Value("${app.mongodb.database.anomaly-detection-db}")
    private String anomalyDetectionDb;

    @Value("${app.mongodb.database.knowledge-base-db}")
    private String knowledgeBaseDb;

    @Value("${app.mongodb.database.scheduler-db}")
    private String schedulerDb;

    @Bean
    public MongoClient mongoClient(){
        return MongoClients.create(uri);
    }

    @Bean
    @Primary
    public MongoTemplate anomalyDetectionMongoTemplate() {
        return new MongoTemplate(mongoClient(), anomalyDetectionDb);
    }

    @Bean
    @Qualifier("knowledgeBaseMongoTemplate")
    public MongoTemplate knowledgeBaseMongoTemplate() {
        return new MongoTemplate(mongoClient(), knowledgeBaseDb);
    }

    @Bean
    public MongoTemplate schedulerMongoTemplate() {
        return new MongoTemplate(mongoClient(), schedulerDb);
    }

}
