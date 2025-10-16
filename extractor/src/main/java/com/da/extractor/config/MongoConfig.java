package com.da.extractor.config;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;

/**
 * Configuración de MongoDB para manejar múltiples bases de datos.
 *
 * Funcionalidades:
 * - Configuración de base de datos de configuraciones (fuente)
 * - Configuración de base de datos de destino (target)
 * - Templates separados para cada base de datos
 * - Beans primarios para inyección por defecto
 */
@Slf4j
@Configuration
public class MongoConfig {

    @Value("${spring.data.mongodb.uri}")
    private String configDatabaseUri;

    @Value("${app.mongodb.target.uri}")
    private String targetDatabaseUri;

    @Value("${spring.data.mongodb.database}")
    private String configDatabaseName;

    @Value("${app.mongodb.target.database}")
    private String targetDatabaseName;

    /**
     * Cliente MongoDB para la base de datos de configuraciones
     */
    @Bean
    @Primary
    public MongoClient configMongoClient() {
        log.info("Configurando cliente MongoDB para base de datos de configuraciones: {}", configDatabaseName);
        return MongoClients.create(configDatabaseUri);
    }

    /**
     * Cliente MongoDB para la base de datos de destino
     */
    @Bean
    public MongoClient targetMongoClient() {
        log.info("Configurando cliente MongoDB para base de datos de destino: {}", targetDatabaseName);
        return MongoClients.create(targetDatabaseUri);
    }

    /**
     * Factory para la base de datos de configuraciones
     */
    @Bean
    @Primary
    public MongoDatabaseFactory configMongoDatabaseFactory() {
        return new SimpleMongoClientDatabaseFactory(configMongoClient(), configDatabaseName);
    }

    /**
     * Factory para la base de datos de destino
     */
    @Bean
    public MongoDatabaseFactory targetMongoDatabaseFactory() {
        return new SimpleMongoClientDatabaseFactory(targetMongoClient(), targetDatabaseName);
    }

    /**
     * Template para operaciones en la base de datos de configuraciones
     */
    @Bean
    @Primary
    public MongoTemplate configMongoTemplate() {
        return new MongoTemplate(configMongoDatabaseFactory());
    }

    /**
     * Template para operaciones en la base de datos de destino
     */
    @Bean
    public MongoTemplate targetMongoTemplate() {
        return new MongoTemplate(targetMongoDatabaseFactory());
    }
}
