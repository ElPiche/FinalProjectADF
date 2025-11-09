package com.da.anomaliesinsightsmodule.service;

import com.da.anomaliesinsightsmodule.entity.DataView;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.Map;

@Service
public class KibanaService {

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    @Value("${kibana.base-url}")
    private String baseUrl;

    public KibanaService(HttpClient httpClient, ObjectMapper objectMapper) {
        this.httpClient = httpClient;
        this.objectMapper = objectMapper;
    }

    public String createDataView(String indexTitle) {
        try {
            DataView dv = new DataView(indexTitle, indexTitle, "@timestamp", true);
            String body = objectMapper.writeValueAsString(Map.of("data_view", dv));

            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/api/data_views/data_view"))
                    .header("kbn-xsrf", "true")
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();

            HttpResponse<String> resp = httpClient.send(req, HttpResponse.BodyHandlers.ofString());

            if (resp.statusCode() == 200 || resp.statusCode() == 201) {
                // En 8.x suele venir como {"data_view":{"id":"...","title":"..."}}
                var root = objectMapper.readTree(resp.body());
                var dvNode = root.has("data_view") ? root.get("data_view") : root;
                return dvNode.get("id").asText();
            }

            if (resp.statusCode() == 409) {
                // Ya existe → buscar por título y devolver su id
                return getDataViewIdByTitle(indexTitle);
            }

            throw new RuntimeException("Create DV error " + resp.statusCode() + ": " + resp.body());

        } catch (Exception e) {
            throw new RuntimeException("Failed to create data view: " + indexTitle, e);
        }
    }


    public String getDataViewIdByTitle(String title) {
        try {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/api/data_views/data_view/list"))
                    .header("kbn-xsrf", "true")
                    .GET().build();

            HttpResponse<String> resp = httpClient.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) return null;

            var arr = objectMapper.readTree(resp.body()).get("data_view");
            // Algunas versiones devuelven {"data_view":[...]} otras {"data_views":[...]} ajusta si hace falta
            var list = arr != null ? arr : objectMapper.readTree(resp.body()).get("data_views");
            if (list == null || !list.isArray()) return null;

            for (var n : list) {
                if (n.get("title").asText().equals(title)) {
                    return n.get("id").asText();
                }
            }
            return null;

        } catch (Exception e) {
            return null;
        }
    }


    public void refreshDataViewFields(String dataViewId) {
        try {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/api/data_views/data_view/" + dataViewId + "/refresh_fields"))
                    .header("kbn-xsrf", "true")
                    .POST(HttpRequest.BodyPublishers.noBody())
                    .build();

            httpClient.send(req, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            // no romper el flujo por esto
            //e.printStackTrace();
            throw new RuntimeException("Failed to refresh data view fields: ", e);
        }
    }

    /*
    public String createSavedSearch(String dataViewId, String title) {
        try {
            String searchSourceJson = """
              {"index":"%s","query":{"language":"kuery","query":""},"filter":[]}
            """.formatted(dataViewId).replace("\n","");

            var body = Map.of(
                    "attributes", Map.of(
                            "title", title,
                            "columns", List.of("@timestamp","algorithm","metric","value","text"),
                            "sort", List.of(List.of("@timestamp","desc")),
                            "kibanaSavedObjectMeta", Map.of("searchSourceJSON", searchSourceJson)
                    )
            );

            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/api/saved_objects/search"))
                    .header("kbn-xsrf", "true")
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(body)))
                    .build();

            HttpResponse<String> resp = httpClient.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() == 200 || resp.statusCode() == 201) {
                return objectMapper.readTree(resp.body()).get("id").asText();
            }
            if (resp.statusCode() == 409) return null;
            throw new RuntimeException("Saved search error " + resp.statusCode() + ": " + resp.body());

        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }


    public String createLens(String dataViewId, String title) {
        try {
            // Estado mínimo de Lens (8.x). Si tu versión cambia, puede requerir pequeños ajustes.
            var lens = Map.of(
                    "attributes", Map.of(
                            "title", title,
                            "description", "",
                            "visualizationType", "lnsXY",
                            "state", Map.of(
                                    "query", Map.of("language","kuery","query",""),
                                    "filters", List.of(),
                                    "adHocDataViews", List.of(),
                                    "datasourceStates", Map.of(
                                            "indexpattern", Map.of(
                                                    "layers", Map.of(
                                                            "layer1", Map.of(
                                                                    "columnOrder", List.of("x","split","y"),
                                                                    "columns", Map.of(
                                                                            "x", Map.of(
                                                                                    "columnId","x",
                                                                                    "operationType","date_histogram",
                                                                                    "sourceField","@timestamp",
                                                                                    "params", Map.of("interval","auto")
                                                                            ),
                                                                            "y", Map.of(
                                                                                    "columnId","y",
                                                                                    "operationType","average",
                                                                                    "sourceField","value",
                                                                                    "isBucketed", false,
                                                                                    "params", Map.of()
                                                                            ),
                                                                            "split", Map.of(
                                                                                    "columnId","split",
                                                                                    "operationType","terms",
                                                                                    "sourceField","metric",
                                                                                    "isBucketed", true,
                                                                                    "params", Map.of(
                                                                                            "size", 5,
                                                                                            "orderBy", Map.of("type","column","columnId","y"),
                                                                                            "orderDirection","desc"
                                                                                    )
                                                                            )
                                                                    )
                                                            )
                                                    )
                                            )
                                    ),
                                    "visualization", Map.of(
                                            "legend", Map.of("isVisible", true, "position", "right"),
                                            "preferredSeriesType", "line",
                                            "layers", List.of(Map.of(
                                                    "layerId","layer1",
                                                    "seriesType","line",
                                                    "xAccessor","x",
                                                    "accessors", List.of("y"),
                                                    "splitAccessor","split"
                                            ))
                                    ),
                                    "references", List.of(
                                            Map.of("type","index-pattern","id",dataViewId,"name","indexpattern-datasource-current-indexpattern"),
                                            Map.of("type","index-pattern","id",dataViewId,"name","indexpattern-datasource-layer-layer1")
                                    )
                            )
                    )
            );

            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/api/saved_objects/lens"))
                    .header("kbn-xsrf", "true")
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(lens)))
                    .build();

            HttpResponse<String> resp = httpClient.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() == 200 || resp.statusCode() == 201) {
                return objectMapper.readTree(resp.body()).get("id").asText();
            }
            if (resp.statusCode() == 409) return null;
            throw new RuntimeException("Lens error " + resp.statusCode() + ": " + resp.body());

        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }


    public String createDashboard(String title, String savedSearchId, String lensId) {
        try {
            String panelsJson = ("[" +
                    (savedSearchId == null ? "" :
                            "{\"type\":\"search\",\"id\":\"" + savedSearchId + "\",\"panelIndex\":\"1\"," +
                                    "\"gridData\":{\"x\":0,\"y\":0,\"w\":24,\"h\":10,\"i\":\"1\"},\"embeddableConfig\":{}}") +
                    (lensId == null ? "" :
                            (savedSearchId == null ? "" : ",") +
                                    "{\"type\":\"lens\",\"id\":\"" + lensId + "\",\"panelIndex\":\"2\"," +
                                    "\"gridData\":{\"x\":0,\"y\":10,\"w\":24,\"h\":16,\"i\":\"2\"},\"embeddableConfig\":{}}")
                    + "]");

            var body = Map.of("attributes", Map.of(
                    "title", title,
                    "timeRestore", false,
                    "panelsJSON", panelsJson
            ));

            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/api/saved_objects/dashboard"))
                    .header("kbn-xsrf", "true")
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(body)))
                    .build();

            HttpResponse<String> resp = httpClient.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() == 200 || resp.statusCode() == 201) {
                return objectMapper.readTree(resp.body()).get("id").asText();
            }
            if (resp.statusCode() == 409) return null;
            throw new RuntimeException("Dashboard error " + resp.statusCode() + ": " + resp.body());

        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }*/
}
