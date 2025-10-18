package com.da.extractor.service;


import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.esql.ElasticsearchEsqlClient;
import co.elastic.clients.elasticsearch.esql.QueryRequest;
import co.elastic.clients.json.JsonpMapper;
import co.elastic.clients.transport.endpoints.BinaryResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.util.Map;

@Service
public class ElasticService {

    @Autowired
    ElasticsearchClient client;

    @Autowired
    JsonpMapper jsonpMapper;

    /// Obtiene información del clúster de Elasticsearch
    public String getClusterInfo() throws Exception {

        return client.info().toString();
    }

    /// Ejecuta una consulta ESQL y devuelve los resultados como un Map
    /// @param query La consulta ESQL a ejecutar
    /// @return Un Map que contiene los resultados de la consulta
    /// @throws IllegalArgumentException Si la respuesta contiene un error
    /// @throws IOException Si ocurre un error al ejecutar la consulta
    public Map<String, Object> executeQuery(String query) throws IllegalArgumentException, IOException {

        IO.println("Executing ESQL Query: " + query);
        ElasticsearchEsqlClient esqlClient = client.esql();

        BinaryResponse binaryResponse = esqlClient.query(QueryRequest.of(builder ->  builder.query(query)));

        InputStream binaryResponseStream = binaryResponse.content();

        ObjectMapper objectMapper = new ObjectMapper();

        // Convertir el InputStream a un Map
        Map<String, Object> resultMap = objectMapper.readValue(new String(binaryResponseStream.readAllBytes()), Map.class);

        if(resultMap.containsKey("error")){
            throw new IllegalArgumentException("Error while executing query: " + resultMap.get("error"));
        }

        return resultMap;
    }
}