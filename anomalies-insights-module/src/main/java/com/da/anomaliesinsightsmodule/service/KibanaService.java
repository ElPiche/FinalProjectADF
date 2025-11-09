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
<<<<<<< Updated upstream
=======
    }*/

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
            int status = resp.statusCode();

            String id;

            if (status == 200 || status == 201) {
                // {"data_view": { "id": ... }}
                var root = objectMapper.readTree(resp.body());
                var dvNode = root.has("data_view") ? root.get("data_view") : root;
                id = dvNode.get("id").asText();

            } else if (status == 409) {
                // Ya existe → buscamos por título
                id = getDataViewIdByTitle(indexTitle);
                if (id == null || id.isBlank()) {
                    throw new RuntimeException("Data view already exists but id not found for title: " + indexTitle);
                }

            } else {
                throw new RuntimeException("Create DV error " + status + ": " + resp.body());
            }

            try {
                refreshDataViewFields(id);
            } catch (Exception ignore) { /* opcional: log.warn */ }

            return id;

        } catch (Exception e) {
            throw new RuntimeException("Failed to create data view: " + indexTitle, e);
        }
>>>>>>> Stashed changes
    }

    public void createDefaultDashboard(String indexName){

<<<<<<< Updated upstream
=======
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


    public String createSavedSearch(String dataViewId, String title) {
        try {
            String searchSourceJson = """
                {"index":"%s","query":{"language":"kuery","query":""},"filter":[]}
                """.formatted(dataViewId).trim();

            var body = Map.of(
                    "attributes", Map.of(
                            "title", title,
                            "columns", List.of("@timestamp","algorithm","metric","value","text"),
                            "sort", List.of(List.of("@timestamp","desc")),
                            "kibanaSavedObjectMeta", Map.of("searchSourceJSON", searchSourceJson)
                    ),
                    "references", List.of(
                            Map.of(
                                    "type", "index-pattern",
                                    "id", dataViewId,
                                    "name", "kibanaSavedObjectMeta.searchSourceJSON.index"
                            )
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

    public String createLensBasic(String dataViewId, String title) {
        try {
            String searchSourceJson = """
          {"index":"%s","query":{"language":"kuery","query":""},"filter":[]}
        """.formatted(dataViewId).trim();

            var body = Map.of(
                    "attributes", Map.of(
                            "title", title,
                            "description", "",
                            "visualizationType", "lnsXY",
                            "state", Map.of(
                                    "query", Map.of("language","kuery","query",""),
                                    "filters", List.of(),
                                    "adHocDataViews", List.of(),
                                    "kibanaSavedObjectMeta", Map.of(
                                            "searchSourceJSON", searchSourceJson
                                    ),
                                    "datasourceStates", Map.of(
                                            "indexpattern", Map.of(
                                                    "layers", Map.of(
                                                            "layer1", Map.of(
                                                                    "indexPatternId", dataViewId,
                                                                    "columnOrder", List.of("x","y"),
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
                                                    "accessors", List.of("y")
                                                    // 👈 sin splitAccessor
                                            ))
                                    )
                            )
                    ),
                    "references", List.of(
                            Map.of("type","index-pattern","id",dataViewId,"name","indexpattern-datasource-current-indexpattern"),
                            Map.of("type","index-pattern","id",dataViewId,"name","indexpattern-datasource-layer-layer1"),
                            Map.of("type","index-pattern","id",dataViewId,"name","kibanaSavedObjectMeta.searchSourceJSON.index")
                    )
            );

            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/api/saved_objects/lens"))
                    .header("kbn-xsrf", "true")
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(body)))
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

    /*
    public String createLens(String dataViewId, String title) {
        try {
            // Estado mínimo de Lens (8.x). Si tu versión cambia, puede requerir pequeños ajustes.
            String searchSourceJson = """
                {"index":"%s","query":{"language":"kuery","query":""},"filter":[]}
                """.formatted(dataViewId).trim();

            var body = Map.of(
                    "attributes", Map.of(
                            "title", title,
                            "description", "",
                            "visualizationType", "lnsXY",
                            // ✅ En Lens, el searchSource va DENTRO de state.kibanaSavedObjectMeta
                            "state", Map.of(
                                    "query", Map.of("language","kuery","query",""),
                                    "filters", List.of(),
                                    "adHocDataViews", List.of(),
                                    "kibanaSavedObjectMeta", Map.of(
                                            "searchSourceJSON", searchSourceJson
                                    ),
                                    "datasourceStates", Map.of(
                                            "indexpattern", Map.of(
                                                    "layers", Map.of(
                                                            "layer1", Map.of(
                                                                    // Recomendado: referenciar explícitamente el Data View
                                                                    "indexPatternId", dataViewId,
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
                                    )
                            )
                    ),
                    // ✅ Las referencias deben ir al NIVEL RAÍZ
                    "references", List.of(
                            Map.of("type","index-pattern","id",dataViewId,"name","indexpattern-datasource-current-indexpattern"),
                            Map.of("type","index-pattern","id",dataViewId,"name","indexpattern-datasource-layer-layer1"),
                            Map.of("type","index-pattern","id",dataViewId,"name","kibanaSavedObjectMeta.searchSourceJSON.index")
                    )
            );

            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/api/saved_objects/lens"))
                    .header("kbn-xsrf", "true")
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(body)))
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
    }*/

    public String createDashboard(String title, String savedSearchId, String lensId) {
        try {
            var panels = new java.util.ArrayList<Map<String, Object>>();
            var refs   = new java.util.ArrayList<Map<String, Object>>();

            // Panel 1: Saved Search
            if (savedSearchId != null) {
                panels.add(Map.of(
                        "type", "search",
                        "id", savedSearchId,
                        "panelIndex", "1",
                        "title", "",
                        // 👇 NECESARIO EN 8.19+ PARA QUE PUEDA RESOLVER searchSource
                        "embeddableConfig", Map.of("savedObjectId", savedSearchId),
                        "gridData", Map.of("x",0,"y",0,"w",24,"h",10,"i","1")
                ));
                refs.add(Map.of("type","search","id",savedSearchId,"name","panel_savedsearch"));
            }

            // Panel 2: Lens
            if (lensId != null) {
                panels.add(Map.of(
                        "type", "lens",
                        "id", lensId,
                        "panelIndex", "2",
                        "title", "",
                        "embeddableConfig", Map.of("savedObjectId", lensId),
                        "gridData", Map.of("x",0,"y",10,"w",24,"h",16,"i","2")
                ));
                refs.add(Map.of("type","lens","id",lensId,"name","panel_lens"));
            }

            var body = Map.of(
                    "attributes", Map.of(
                            "title", title,
                            "timeRestore", false,
                            "optionsJSON", "{\"useMargins\":true,\"syncColors\":false,\"hidePanelTitles\":false}",
                            "panelsJSON", objectMapper.writeValueAsString(panels)
                    ),
                    "references", refs
            );

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
>>>>>>> Stashed changes
    }

    public String createDashboardWithRefs(String title, String savedSearchId, String lensId) {
        try {
            var panels = new java.util.ArrayList<Map<String, Object>>();
            var refs   = new java.util.ArrayList<Map<String, Object>>();

            if (savedSearchId != null) {
                panels.add(Map.of(
                        "type", "search",
                        "panelRefName", "panel_savedsearch",
                        "panelIndex", "1",
                        "title", "",
                        "version", "8.19.3", // 👈 importante en 8.19
                        "embeddableConfig", Map.of(), // no savedObjectId cuando usás refs
                        "gridData", Map.of("x",0,"y",0,"w",24,"h",10,"i","1")
                ));
                refs.add(Map.of("type","search","id",savedSearchId,"name","panel_savedsearch"));
            }

            if (lensId != null) {
                panels.add(Map.of(
                        "type", "lens",
                        "panelRefName", "panel_lens",
                        "panelIndex", "2",
                        "title", "",
                        "version", "8.19.3",
                        "embeddableConfig", Map.of(),
                        "gridData", Map.of("x",0,"y",10,"w",24,"h",16,"i","2")
                ));
                refs.add(Map.of("type","lens","id",lensId,"name","panel_lens"));
            }

            var body = Map.of(
                    "attributes", Map.of(
                            "title", title,
                            "timeRestore", false,
                            "optionsJSON", "{\"useMargins\":true,\"syncColors\":false,\"hidePanelTitles\":false}",
                            "panelsJSON", objectMapper.writeValueAsString(panels)
                    ),
                    "references", refs
            );

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
    }

    public String createDashboardDirect(String title, String savedSearchId, String lensId) {
        try {
            var panels = new java.util.ArrayList<Map<String, Object>>();

            if (savedSearchId != null) {
                panels.add(Map.of(
                        "type", "search",
                        "id", savedSearchId,
                        "panelIndex", "1",
                        "title", "",
                        "version", "8.19.3", // 👈 importante
                        "embeddableConfig", Map.of("savedObjectId", savedSearchId),
                        "gridData", Map.of("x",0,"y",0,"w",24,"h",10,"i","1")
                ));
            }

            if (lensId != null) {
                panels.add(Map.of(
                        "type", "lens",
                        "id", lensId,
                        "panelIndex", "2",
                        "title", "",
                        "version", "8.19.3",
                        "embeddableConfig", Map.of("savedObjectId", lensId),
                        "gridData", Map.of("x",0,"y",10,"w",24,"h",16,"i","2")
                ));
            }

            var body = Map.of(
                    "attributes", Map.of(
                            "title", title,
                            "timeRestore", false,
                            "optionsJSON", "{\"useMargins\":true,\"syncColors\":false,\"hidePanelTitles\":false}",
                            "panelsJSON", objectMapper.writeValueAsString(panels)
                    )
                    // sin references cuando usás id directo
            );

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
    }

    /*
    public String createDashboard(String title, String savedSearchId, String lensId) {
        try {
            StringBuilder panels = new StringBuilder("[");
            boolean first = true;

            if (savedSearchId != null) {
                if (!first) panels.append(",");
                first = false;
                panels.append("{")
                        .append("\"type\":\"search\",")
                        .append("\"id\":\"").append(savedSearchId).append("\",")
                        .append("\"panelIndex\":\"1\",") // <- requerido
                        .append("\"title\":\"\",")       // <- requerido (puede ser "")
                        .append("\"embeddableConfig\":{},")
                        .append("\"gridData\":{")
                        .append("\"x\":0,\"y\":0,\"w\":24,\"h\":10,\"i\":\"1\"")
                        .append("}")
                        .append("}");
            }

            if (lensId != null) {
                if (!first) panels.append(",");
                panels.append("{")
                        .append("\"type\":\"lens\",")
                        .append("\"id\":\"").append(lensId).append("\",")
                        .append("\"panelIndex\":\"2\",") // <- requerido
                        .append("\"title\":\"\",")       // <- requerido
                        .append("\"embeddableConfig\":{},")
                        .append("\"gridData\":{")
                        .append("\"x\":0,\"y\":10,\"w\":24,\"h\":16,\"i\":\"2\"")
                        .append("}")
                        .append("}");
            }
            panels.append("]");

            var body = Map.of(
                    "attributes", Map.of(
                            "title", title,
                            "timeRestore", false,
                            "optionsJSON", "{\"useMargins\":true,\"syncColors\":false,\"hidePanelTitles\":false}",
                            "panelsJSON", panels.toString()
                    )
                    // Nota: cuando usás "id" directo en cada panel, "references" puede omitirse.
            );

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
