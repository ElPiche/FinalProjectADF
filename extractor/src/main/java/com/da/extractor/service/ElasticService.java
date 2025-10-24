package com.da.extractor.service;


import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.sql.*;
import co.elastic.clients.elasticsearch.sql.query.SqlFormat;
import co.elastic.clients.elasticsearch.xpack.usage.Sql;
import co.elastic.clients.json.JsonData;
import co.elastic.clients.json.JsonpMapper;
import co.elastic.clients.transport.endpoints.BinaryResponse;
import com.da.extractor.model.ElasticResponse;
import com.da.extractor.utils.Utils;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.constraints.Null;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.io.Reader;
import java.util.ArrayList;
import java.util.HashMap;
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
    /*
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
    }*/

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
//        ElasticsearchEsqlClient esqlClient = client.esql();

//        BinaryResponse binaryResponse = esqlClient.query(QueryRequest.of(builder ->  builder.query(query).format(EsqlFormat.Json)));

//        try (InputStream is = binaryResponse.content()) {
//            byte[] bytes = is.readAllBytes();
//
//            // (Opcional) Loguear el JSON crudo para debug
//            String rawJson = new String(bytes);
//            IO.println("Raw ESQL JSON:\n" + rawJson);
//
//            // 3) Parsear a Map
//            ObjectMapper mapper = new ObjectMapper();
//            Map<String, Object> root = mapper.readValue(bytes, Map.class);
//
//            // 4) Manejo de error si el JSON trae "error"
//            if (root.containsKey("error")) {
//                throw new IllegalArgumentException("Error while executing query: " + root.get("error"));
//            }
//
//            return root;
//
//        }
    }

    public void clearCursor(String cursor) throws IOException {
        sqlClient.clearCursor(ClearCursorRequest.of(builder -> builder.cursor(cursor)));
    }

    @SuppressWarnings("unchecked")
    public void printEsqlResult(Map<String, Object> esqlJson) {
        List<Map<String, Object>> columns = (List<Map<String, Object>>) esqlJson.get("columns");
        List<List<Object>> values = (List<List<Object>>) esqlJson.get("values");

        if (columns == null || values == null) {
            IO.println("La respuesta no tiene el formato ESQL esperado (columns/values).");
            IO.println(esqlJson.toString());
            return;
        }

        // Encabezados
        StringBuilder header = new StringBuilder();
        for (int i = 0; i < columns.size(); i++) {
            if (i > 0) header.append(" | ");
            header.append(columns.get(i).get("name"));
        }
        IO.println(header.toString());

        // Filas
        for (List<Object> row : values) {
            StringBuilder line = new StringBuilder();
            for (int i = 0; i < row.size(); i++) {
                if (i > 0) line.append(" | ");
                line.append(row.get(i));
            }
            IO.println(line.toString());
        }
    }

}