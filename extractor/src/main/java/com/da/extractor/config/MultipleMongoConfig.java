package com.da.extractor.config;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;
import org.springframework.data.mongodb.core.convert.*;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;

import java.util.List;

@Configuration
public class MultipleMongoConfig {

    @Value("${spring.data.mongodb.uri}")
    private String uri;

    @Value("${app.mongodb.database.anomaly-detection-db}")
    private String anomalyDetectionDb;

    @Value("${app.mongodb.database.knowledge-base-db}")
    private String knowledgeBaseDb;

    @Value("${app.mongodb.database.extractor-db}")
    private String extractorDb;

    @Bean
    public MongoClient mongoClient(){
        return MongoClients.create(uri);
    }

    @Bean(name = "mongoCustomConversions")
    public MongoCustomConversions mongoCustomConversions() {
        return new MongoCustomConversions(List.of(StringToDateReadingConverter.INSTANCE));
    }

    private MongoTemplate buildTemplate(String dbName, MongoClient client, MongoCustomConversions conversions) {
        MongoDatabaseFactory factory = new SimpleMongoClientDatabaseFactory(client, dbName);
        MongoMappingContext context = new MongoMappingContext();
        MappingMongoConverter converter = new MappingMongoConverter(new DefaultDbRefResolver(factory), context);
        converter.setCustomConversions(conversions);
        converter.afterPropertiesSet();
        return new MongoTemplate(factory, converter);
    }

    @Bean
    @Primary
    public MongoTemplate anomalyDetectionMongoTemplate(MongoClient client, @Qualifier("mongoCustomConversions") MongoCustomConversions conversions) {
        return buildTemplate(anomalyDetectionDb, client, conversions);
    }

    @Bean
    @Qualifier("knowledgeBaseMongoTemplate")
    public MongoTemplate knowledgeBaseMongoTemplate(MongoClient client, @Qualifier("mongoCustomConversions") MongoCustomConversions conversions) {
        return buildTemplate(knowledgeBaseDb, client, conversions);
    }

    @Bean
    public MongoTemplate extractorMongoTemplate(MongoClient client, @Qualifier("mongoCustomConversions") MongoCustomConversions conversions) {
        return buildTemplate(extractorDb, client, conversions);
    }
}
