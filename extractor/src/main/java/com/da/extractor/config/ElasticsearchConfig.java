package com.da.extractor.config;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.json.jackson.JacksonJsonpMapper;
import co.elastic.clients.transport.ElasticsearchTransport;
import co.elastic.clients.transport.rest_client.RestClientTransport;
import lombok.extern.slf4j.Slf4j;
import org.apache.http.HttpHost;
import org.apache.http.auth.AuthScope;
import org.apache.http.auth.UsernamePasswordCredentials;
import org.apache.http.client.CredentialsProvider;
import org.apache.http.impl.client.BasicCredentialsProvider;
import org.elasticsearch.client.RestClient;
import org.elasticsearch.client.RestClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.StringUtils;

/**
 * Configuración de conexión a Elasticsearch.
 *
 * Funcionalidades:
 * - Configuración del cliente Elasticsearch
 * - Soporte para autenticación básica
 * - Manejo de conexión HTTP/HTTPS
 * - Bean singleton para inyección de dependencias
 */
@Slf4j
@Configuration
public class ElasticsearchConfig {

    @Value("${app.elasticsearch.host}")
    private String host;

    @Value("${app.elasticsearch.port}")
    private int port;

    @Value("${app.elasticsearch.protocol}")
    private String protocol;

    @Value("${app.elasticsearch.username:}")
    private String username;

    @Value("${app.elasticsearch.password:}")
    private String password;

    /**
     * Crea y configura el cliente de Elasticsearch
     * @return Cliente configurado para conectar a Elasticsearch
     */
    @Bean
    public ElasticsearchClient elasticsearchClient() {
        log.info("Configurando cliente Elasticsearch para {}://{}:{}", protocol, host, port);

        // Crear el host HTTP
        HttpHost httpHost = new HttpHost(host, port, protocol);

        // Builder del cliente REST
        RestClientBuilder builder = RestClient.builder(httpHost);

        // Configurar autenticación si está disponible
        if (StringUtils.hasText(username) && StringUtils.hasText(password)) {
            log.info("Configurando autenticación básica para Elasticsearch");
            CredentialsProvider credentialsProvider = new BasicCredentialsProvider();
            credentialsProvider.setCredentials(AuthScope.ANY,
                    new UsernamePasswordCredentials(username, password));

            builder.setHttpClientConfigCallback(httpClientBuilder ->
                    httpClientBuilder.setDefaultCredentialsProvider(credentialsProvider));
        }

        // Crear el cliente REST
        RestClient restClient = builder.build();

        // Crear el transporte con Jackson JSON mapper
        ElasticsearchTransport transport = new RestClientTransport(
                restClient, new JacksonJsonpMapper());

        return new ElasticsearchClient(transport);
    }
}
