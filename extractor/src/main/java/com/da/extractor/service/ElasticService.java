package com.da.extractor.service;


import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.sql.*;
import co.elastic.clients.elasticsearch.sql.query.SqlFormat;
import co.elastic.clients.json.JsonpMapper;
import jakarta.validation.constraints.Null;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.List;
import java.util.Map;

@Service
public class ElasticService {

    final ElasticsearchClient client;

    final JsonpMapper jsonpMapper;

    final ElasticsearchSqlClient sqlClient;

    final int FETCH_SIZE = 1000;

    public ElasticService(ElasticsearchClient client, JsonpMapper jsonpMapper) {
        this.client = client;
        this.jsonpMapper = jsonpMapper;
        this.sqlClient = client.sql();
    }

    /// Obtiene información del clúster de Elasticsearch
    public String getClusterInfo() throws Exception {
        return client.info().toString();
    }

    /// Ejecuta una consulta ESQL y devuelve los resultados como un Map
    /// @param query La consulta ESQL a ejecutar
    /// @return Un Map que contiene los resultados de la consulta
    /// @throws IllegalArgumentException Si la respuesta contiene un error
    /// @throws IOException Si ocurre un error al ejecutar la consulta
    public QueryResponse executeQuery(String query, @Null String requestCursor)
            throws IllegalArgumentException, IOException {

        IO.println("Executing ESQL Query: " + query);

        return sqlClient.query(QueryRequest.of(builder -> {

            builder.query(query).allowPartialSearchResults(true).format(SqlFormat.Json).fetchSize(FETCH_SIZE);

            if(requestCursor != null){
                builder.cursor(requestCursor);
            }

            return builder;

        }));
    }

    public void clearCursor(String cursor) throws IOException {
        sqlClient.clearCursor(ClearCursorRequest.of(builder -> builder.cursor(cursor)));
    }

}