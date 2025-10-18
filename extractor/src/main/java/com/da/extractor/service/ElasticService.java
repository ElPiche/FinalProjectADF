package com.da.extractor.service;


import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.esql.ElasticsearchEsqlClient;
import co.elastic.clients.elasticsearch.esql.QueryRequest;
import co.elastic.clients.json.JsonpMapper;
import co.elastic.clients.transport.endpoints.BinaryResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.io.InputStream;
import java.util.Map;

@Service
public class ElasticService {

    @Autowired
    ElasticsearchClient client;

    @Autowired
    JsonpMapper jsonpMapper;

    public String getClusterInfo() throws Exception {

        return client.info().toString();
    }

    public void executeQuery(String query) throws Exception {

        IO.println("Executing ESQL Query: " + query);
        ElasticsearchEsqlClient esqlClient = client.esql();

        BinaryResponse binaryResponse = esqlClient.query(QueryRequest.of(builder ->  builder.query(query)));

        InputStream binaryResponseStream = binaryResponse.content();


        String result = new String(binaryResponseStream.readAllBytes());

        ObjectMapper objectMapper = new ObjectMapper();
        Map resultMap = objectMapper.readValue(binaryResponseStream, Map.class);

        resultMap.forEach((key, value) ->
                IO.println("Key: " + key + ", Value: " + value)
        );
    }
}