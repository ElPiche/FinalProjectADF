package com.da.anomaliesinsightsmodule.service;

import com.da.anomaliesinsightsmodule.entity.DataView;
import com.fasterxml.jackson.databind.ObjectMapper;
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
    private String baseUrl = "http://localhost:5602";

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

    public String createDashboardWithEmbeddedLens(String title, String dataViewId, String savedSearchId) {
        try {
            var panels = new java.util.ArrayList<Map<String, Object>>();
            var references = new java.util.ArrayList<Map<String, Object>>();

            if (savedSearchId != null && !savedSearchId.isBlank()) {
                panels.add(Map.of(
                        "type", "search",
                        "panelRefName", "panel_0",
                        "embeddableConfig", Map.of("savedObjectId", savedSearchId, "title", ""),
                        "panelIndex", "0",
                        "gridData", Map.of("x", 0, "y", 0, "w", 48, "h", 6, "i", "0")
                ));
                references.add(Map.of(
                        "type", "search",
                        "id", savedSearchId,
                        "name", "0:panel_0"
                ));
            }

            Map<String, Object> lens1 = Map.of(
                    "type", "lens",
                    "panelIndex", "1",
                    "embeddableConfig", Map.of(
                            "attributes", Map.of(
                                    "title", "Suma de value",
                                    "visualizationType", "lnsXY",
                                    "type", "lens",
                                    "references", List.of(Map.of(
                                            "type", "index-pattern",
                                            "id", dataViewId,
                                            "name", "indexpattern-datasource-layer-layer1"
                                    )),
                                    "state", Map.of(
                                            "filters", List.of(),
                                            "adHocDataViews", Map.of(),
                                            "visualization", Map.of(
                                                    "title", "",
                                                    "preferredSeriesType", "bar_stacked",
                                                    "layers", List.of(Map.of(
                                                            "accessors", List.of("y"),
                                                            "layerType", "data",
                                                            "seriesType", "bar_stacked",
                                                            "layerId", "layer1",
                                                            "xAccessor", "x"
                                                    )),
                                                    "legend", Map.of("isVisible", true, "position", "right")
                                            ),
                                            "datasourceStates", Map.of(
                                                    "formBased", Map.of(
                                                            "layers", Map.of(
                                                                    "layer1", Map.of(
                                                                            "columns", Map.of(
                                                                                    "x", Map.of(
                                                                                            "params", Map.of("interval", "auto"),
                                                                                            "isBucketed", true,
                                                                                            "operationType", "date_histogram",
                                                                                            "sourceField", "@timestamp",
                                                                                            "label", "@timestamp",
                                                                                            "dataType", "date"
                                                                                    ),
                                                                                    "y", Map.of(
                                                                                            "params", Map.of(),
                                                                                            "isBucketed", false,
                                                                                            "operationType", "sum",
                                                                                            "sourceField", "value",
                                                                                            "label", "Suma de value",
                                                                                            "dataType", "number"
                                                                                    )
                                                                            ),
                                                                            "sampling", 1,
                                                                            "columnOrder", List.of("x", "y")
                                                                    )
                                                            )
                                                    )
                                            ),
                                            "query", Map.of("query", "", "language", "kuery")
                                    )
                            )
                    ),
                    "gridData", Map.of("x", 0, "y", 6, "w", 24, "h", 15, "i", "1"),
                    "version", "8.19.3"
            );

            Map<String, Object> lens2 = Map.of(
                    "type", "lens",
                    "panelIndex", "2",
                    "embeddableConfig", Map.of(
                            "attributes", Map.of(
                                    "title", "Conteo de documentos",
                                    "visualizationType", "lnsXY",
                                    "type", "lens",
                                    "references", List.of(Map.of(
                                            "type", "index-pattern",
                                            "id", dataViewId,
                                            "name", "indexpattern-datasource-layer-layer2"
                                    )),
                                    "state", Map.of(
                                            "filters", List.of(),
                                            "adHocDataViews", Map.of(),
                                            "visualization", Map.of(
                                                    "title", "",
                                                    "preferredSeriesType", "bar_stacked",
                                                    "layers", List.of(Map.of(
                                                            "accessors", List.of("count"),
                                                            "layerType", "data",
                                                            "seriesType", "bar_stacked",
                                                            "layerId", "layer2",
                                                            "xAccessor", "x"
                                                    )),
                                                    "legend", Map.of("isVisible", true, "position", "right")
                                            ),
                                            "datasourceStates", Map.of(
                                                    "formBased", Map.of(
                                                            "layers", Map.of(
                                                                    "layer2", Map.of(
                                                                            "columns", Map.of(
                                                                                    "x", Map.of(
                                                                                            "params", Map.of("interval", "auto"),
                                                                                            "isBucketed", true,
                                                                                            "operationType", "date_histogram",
                                                                                            "sourceField", "@timestamp",
                                                                                            "label", "@timestamp",
                                                                                            "dataType", "date"
                                                                                    ),
                                                                                    "count", Map.of(
                                                                                            "label", "Count of value",
                                                                                            "dataType", "number",
                                                                                            "operationType", "count",
                                                                                            "sourceField", "value",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of("emptyAsNull", true)
                                                                                    )
                                                                            ),
                                                                            "sampling", 1,
                                                                            "columnOrder", List.of("x", "count"),
                                                                            "indexPatternId", dataViewId,
                                                                            "incompleteColumns", Map.of()
                                                                    )
                                                            ),
                                                            "currentIndexPatternId", dataViewId
                                                    )
                                            ),
                                            "query", Map.of("query", "", "language", "kuery")
                                    )
                            )
                    ),
                    "gridData", Map.of("x", 24, "y", 6, "w", 24, "h", 15, "i", "2"),
                    "version", "8.19.3"
            );

            panels.add(lens1);
            panels.add(lens2);

            references.add(Map.of("type", "index-pattern", "id", dataViewId, "name", "1:indexpattern-datasource-layer-layer1"));
            references.add(Map.of("type", "index-pattern", "id", dataViewId, "name", "2:indexpattern-datasource-layer-layer2"));

            var body = Map.of(
                    "attributes", Map.of(
                            "title", title,
                            "version", 3,
                            "description", "",
                            "timeRestore", false,
                            "controlGroupInput", Map.of(
                                    "chainingSystem", "HIERARCHICAL",
                                    "controlStyle", "oneLine",
                                    "showApplySelections", false,
                                    "ignoreParentSettingsJSON", "{\"ignoreFilters\":false,\"ignoreQuery\":false,\"ignoreTimerange\":false,\"ignoreValidations\":false}",
                                    "panelsJSON", "{}"
                            ),
                            "optionsJSON", "{\"useMargins\":true,\"syncColors\":false,\"syncCursor\":true,\"syncTooltips\":true,\"hidePanelTitles\":false}",
                            "panelsJSON", objectMapper.writeValueAsString(panels),
                            "kibanaSavedObjectMeta", Map.of(
                                    "searchSourceJSON", "{\"filter\":[],\"query\":{\"query\":\"\",\"language\":\"kuery\"}}"
                            )
                    ),
                    "references", references
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
            throw new RuntimeException("Dashboard error " + resp.statusCode() + ": " + resp.body());

        } catch (Exception e) {
            throw new RuntimeException("Error creating dashboard with embedded lens", e);
        }
    }


}
