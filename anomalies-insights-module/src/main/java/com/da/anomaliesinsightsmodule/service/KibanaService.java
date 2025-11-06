package com.da.anomaliesinsightsmodule.service;

import com.da.anomaliesinsightsmodule.entity.DataView;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

@Service
public class KibanaService {

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private String baseUrl = "http://kibana-anomalies:5602";

    public KibanaService(HttpClient httpClient, ObjectMapper objectMapper) {
        this.httpClient = httpClient;
        this.objectMapper = objectMapper;
    }


    public void createDataView(String indexName){
        try {
            // JSON body
            DataView dataView = new DataView(
                    indexName,
                    indexName,
                    "@timestamp",
                    true
            );


            // Kibana necesita que el JSON tenga la clave "data_view"
            Map<String, Object> payload = Map.of("data_view", dataView);

            String jsonBody = objectMapper.writeValueAsString(payload);

            // Build request
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/api/data_views/data_view"))
                    .header("Content-Type", "application/json")
                    .header("kbn-xsrf", "true")
                    .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
                    .build();

            // Send request
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            // Evaluate response
            if (response.statusCode() == 200 || response.statusCode() == 201) {

                System.out.println("✅ Data view created: " + indexName);

            } else if (response.statusCode() == 409) {

                System.out.println("⚠️ Data view already exists: " + indexName);

            } else {

                System.err.printf("❌ Kibana responded %d: %s%n", response.statusCode(), response.body());

            }

        } catch (Exception e) {

            e.printStackTrace();
            System.err.println("❌ Failed to create Data View for " + indexName + ": " + e.getMessage());

        }
    }

    public void createDefaultDashboard(String indexName){

    }
}
