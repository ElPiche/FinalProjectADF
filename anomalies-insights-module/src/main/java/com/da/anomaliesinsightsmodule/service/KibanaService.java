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

            int status = resp.statusCode();

            String id;

            if (status == 200 || status == 201) {
                // {"data_view": { "id": ... }}
                var root = objectMapper.readTree(resp.body());
                var dvNode = root.has("data_view") ? root.get("data_view") : root;
                id = dvNode.get("id").asText();

            } else if (status == 409 || (status == 400 && resp.body().contains("Duplicate"))) {
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
                    .uri(URI.create(baseUrl + "/api/data_views"))
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

            // Panel 0: Saved Search (Anomaly Details Table)
            if (savedSearchId != null && !savedSearchId.isBlank()) {
                panels.add(Map.of(
                        "type", "search",
                        "panelRefName", "panel_0",
                        "embeddableConfig", Map.of("savedObjectId", savedSearchId, "title", "📋 Anomaly Details"),
                        "panelIndex", "0",
                        "gridData", Map.of("x", 0, "y", 0, "w", 48, "h", 8, "i", "0")
                ));
                references.add(Map.of(
                        "type", "search",
                        "id", savedSearchId,
                        "name", "0:panel_0"
                ));
            }

            // Panel 1: Total Anomalies Metric
            Map<String, Object> metricPanel = Map.of(
                    "type", "lens",
                    "panelIndex", "1",
                    "embeddableConfig", Map.of(
                            "attributes", Map.of(
                                    "title", "🚨 Total Anomalies",
                                    "visualizationType", "lnsMetric",
                                    "type", "lens",
                                    "references", List.of(Map.of(
                                            "type", "index-pattern",
                                            "id", dataViewId,
                                            "name", "indexpattern-datasource-layer-metric1"
                                    )),
                                    "state", Map.of(
                                            "filters", List.of(),
                                            "adHocDataViews", Map.of(),
                                            "visualization", Map.of(
                                                    "layerId", "metric1",
                                                    "layerType", "data",
                                                    "metricAccessor", "count"
                                            ),
                                            "datasourceStates", Map.of(
                                                    "formBased", Map.of(
                                                            "layers", Map.of(
                                                                    "metric1", Map.of(
                                                                            "columns", Map.of(
                                                                                    "count", Map.of(
                                                                                            "label", "Total Anomalies",
                                                                                            "dataType", "number",
                                                                                            "operationType", "count",
                                                                                            "sourceField", "___records___",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of()
                                                                                    )
                                                                            ),
                                                                            "columnOrder", List.of("count")
                                                                    )
                                                            )
                                                    )
                                            ),
                                            "query", Map.of("query", "", "language", "kuery")
                                    )
                            )
                    ),
                    "gridData", Map.of("x", 0, "y", 8, "w", 8, "h", 6, "i", "1"),
                    "version", "8.19.3"
            );
            panels.add(metricPanel);
            references.add(Map.of("type", "index-pattern", "id", dataViewId, "name", "1:indexpattern-datasource-layer-metric1"));

            // Panel 2: Average Value Metric
            Map<String, Object> avgMetric = Map.of(
                    "type", "lens",
                    "panelIndex", "2",
                    "embeddableConfig", Map.of(
                            "attributes", Map.of(
                                    "title", "📊 Avg Anomaly Value",
                                    "visualizationType", "lnsMetric",
                                    "type", "lens",
                                    "references", List.of(Map.of(
                                            "type", "index-pattern",
                                            "id", dataViewId,
                                            "name", "indexpattern-datasource-layer-metric2"
                                    )),
                                    "state", Map.of(
                                            "filters", List.of(),
                                            "adHocDataViews", Map.of(),
                                            "visualization", Map.of(
                                                    "layerId", "metric2",
                                                    "layerType", "data",
                                                    "metricAccessor", "avg"
                                            ),
                                            "datasourceStates", Map.of(
                                                    "formBased", Map.of(
                                                            "layers", Map.of(
                                                                    "metric2", Map.of(
                                                                            "columns", Map.of(
                                                                                    "avg", Map.of(
                                                                                            "label", "Average Value",
                                                                                            "dataType", "number",
                                                                                            "operationType", "average",
                                                                                            "sourceField", "value",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of()
                                                                                    )
                                                                            ),
                                                                            "columnOrder", List.of("avg")
                                                                    )
                                                            )
                                                    )
                                            ),
                                            "query", Map.of("query", "", "language", "kuery")
                                    )
                            )
                    ),
                    "gridData", Map.of("x", 8, "y", 8, "w", 8, "h", 6, "i", "2"),
                    "version", "8.19.3"
            );
            panels.add(avgMetric);
            references.add(Map.of("type", "index-pattern", "id", dataViewId, "name", "2:indexpattern-datasource-layer-metric2"));

            // Panel 3: Max Z-Score Metric
            Map<String, Object> maxZScore = Map.of(
                    "type", "lens",
                    "panelIndex", "3",
                    "embeddableConfig", Map.of(
                            "attributes", Map.of(
                                    "title", "⚡ Max Z-Score",
                                    "visualizationType", "lnsMetric",
                                    "type", "lens",
                                    "references", List.of(Map.of(
                                            "type", "index-pattern",
                                            "id", dataViewId,
                                            "name", "indexpattern-datasource-layer-metric3"
                                    )),
                                    "state", Map.of(
                                            "filters", List.of(),
                                            "adHocDataViews", Map.of(),
                                            "visualization", Map.of(
                                                    "layerId", "metric3",
                                                    "layerType", "data",
                                                    "metricAccessor", "maxz"
                                            ),
                                            "datasourceStates", Map.of(
                                                    "formBased", Map.of(
                                                            "layers", Map.of(
                                                                    "metric3", Map.of(
                                                                            "columns", Map.of(
                                                                                    "maxz", Map.of(
                                                                                            "label", "Max Z-Score",
                                                                                            "dataType", "number",
                                                                                            "operationType", "max",
                                                                                            "sourceField", "algorithm_details.z_score",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of()
                                                                                    )
                                                                            ),
                                                                            "columnOrder", List.of("maxz")
                                                                    )
                                                            )
                                                    )
                                            ),
                                            "query", Map.of("query", "", "language", "kuery")
                                    )
                            )
                    ),
                    "gridData", Map.of("x", 16, "y", 8, "w", 8, "h", 6, "i", "3"),
                    "version", "8.19.3"
            );
            panels.add(maxZScore);
            references.add(Map.of("type", "index-pattern", "id", dataViewId, "name", "3:indexpattern-datasource-layer-metric3"));

            // Panel 4: Anomalies by KB Name (Pie Chart)
            Map<String, Object> kbPie = Map.of(
                    "type", "lens",
                    "panelIndex", "4",
                    "embeddableConfig", Map.of(
                            "attributes", Map.of(
                                    "title", "🎯 Anomalies by Knowledge Base",
                                    "visualizationType", "lnsPie",
                                    "type", "lens",
                                    "references", List.of(Map.of(
                                            "type", "index-pattern",
                                            "id", dataViewId,
                                            "name", "indexpattern-datasource-layer-pie1"
                                    )),
                                    "state", Map.of(
                                            "filters", List.of(),
                                            "adHocDataViews", Map.of(),
                                            "visualization", Map.of(
                                                    "shape", "donut",
                                                    "layers", List.of(Map.of(
                                                            "layerId", "pie1",
                                                            "primaryGroups", List.of("kb"),
                                                            "metrics", List.of("cnt"),
                                                            "numberDisplay", "percent",
                                                            "categoryDisplay", "default",
                                                            "legendDisplay", "show",
                                                            "nestedLegend", false,
                                                            "layerType", "data"
                                                    ))
                                            ),
                                            "datasourceStates", Map.of(
                                                    "formBased", Map.of(
                                                            "layers", Map.of(
                                                                    "pie1", Map.of(
                                                                            "columns", Map.of(
                                                                                    "kb", Map.of(
                                                                                            "label", "KB Name",
                                                                                            "dataType", "string",
                                                                                            "operationType", "terms",
                                                                                            "sourceField", "kb_name.keyword",
                                                                                            "isBucketed", true,
                                                                                            "params", Map.of("size", 10, "orderBy", Map.of("type", "column", "columnId", "cnt"), "orderDirection", "desc")
                                                                                    ),
                                                                                    "cnt", Map.of(
                                                                                            "label", "Count",
                                                                                            "dataType", "number",
                                                                                            "operationType", "count",
                                                                                            "sourceField", "___records___",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of()
                                                                                    )
                                                                            ),
                                                                            "columnOrder", List.of("kb", "cnt")
                                                                    )
                                                            )
                                                    )
                                            ),
                                            "query", Map.of("query", "", "language", "kuery")
                                    )
                            )
                    ),
                    "gridData", Map.of("x", 24, "y", 8, "w", 12, "h", 12, "i", "4"),
                    "version", "8.19.3"
            );
            panels.add(kbPie);
            references.add(Map.of("type", "index-pattern", "id", dataViewId, "name", "4:indexpattern-datasource-layer-pie1"));

            // Panel 5: Anomalies by Algorithm (Pie Chart)
            Map<String, Object> algPie = Map.of(
                    "type", "lens",
                    "panelIndex", "5",
                    "embeddableConfig", Map.of(
                            "attributes", Map.of(
                                    "title", "🔬 Anomalies by Algorithm",
                                    "visualizationType", "lnsPie",
                                    "type", "lens",
                                    "references", List.of(Map.of(
                                            "type", "index-pattern",
                                            "id", dataViewId,
                                            "name", "indexpattern-datasource-layer-pie2"
                                    )),
                                    "state", Map.of(
                                            "filters", List.of(),
                                            "adHocDataViews", Map.of(),
                                            "visualization", Map.of(
                                                    "shape", "pie",
                                                    "layers", List.of(Map.of(
                                                            "layerId", "pie2",
                                                            "primaryGroups", List.of("alg"),
                                                            "metrics", List.of("cnt"),
                                                            "numberDisplay", "value",
                                                            "categoryDisplay", "default",
                                                            "legendDisplay", "show",
                                                            "nestedLegend", false,
                                                            "layerType", "data"
                                                    ))
                                            ),
                                            "datasourceStates", Map.of(
                                                    "formBased", Map.of(
                                                            "layers", Map.of(
                                                                    "pie2", Map.of(
                                                                            "columns", Map.of(
                                                                                    "alg", Map.of(
                                                                                            "label", "Algorithm",
                                                                                            "dataType", "string",
                                                                                            "operationType", "terms",
                                                                                            "sourceField", "algorithm.keyword",
                                                                                            "isBucketed", true,
                                                                                            "params", Map.of("size", 10, "orderBy", Map.of("type", "column", "columnId", "cnt"), "orderDirection", "desc")
                                                                                    ),
                                                                                    "cnt", Map.of(
                                                                                            "label", "Count",
                                                                                            "dataType", "number",
                                                                                            "operationType", "count",
                                                                                            "sourceField", "___records___",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of()
                                                                                    )
                                                                            ),
                                                                            "columnOrder", List.of("alg", "cnt")
                                                                    )
                                                            )
                                                    )
                                            ),
                                            "query", Map.of("query", "", "language", "kuery")
                                    )
                            )
                    ),
                    "gridData", Map.of("x", 36, "y", 8, "w", 12, "h", 12, "i", "5"),
                    "version", "8.19.3"
            );
            panels.add(algPie);
            references.add(Map.of("type", "index-pattern", "id", dataViewId, "name", "5:indexpattern-datasource-layer-pie2"));

            // Panel 6: Anomalies Timeline (Area Chart)
            Map<String, Object> timeline = Map.of(
                    "type", "lens",
                    "panelIndex", "6",
                    "embeddableConfig", Map.of(
                            "attributes", Map.of(
                                    "title", "📈 Anomalies Timeline",
                                    "visualizationType", "lnsXY",
                                    "type", "lens",
                                    "references", List.of(Map.of(
                                            "type", "index-pattern",
                                            "id", dataViewId,
                                            "name", "indexpattern-datasource-layer-timeline"
                                    )),
                                    "state", Map.of(
                                            "filters", List.of(),
                                            "adHocDataViews", Map.of(),
                                            "visualization", Map.of(
                                                    "title", "",
                                                    "preferredSeriesType", "area",
                                                    "layers", List.of(Map.of(
                                                            "accessors", List.of("count"),
                                                            "layerType", "data",
                                                            "seriesType", "area",
                                                            "layerId", "timeline",
                                                            "xAccessor", "time",
                                                            "splitAccessor", "kb"
                                                    )),
                                                    "legend", Map.of("isVisible", true, "position", "right")
                                            ),
                                            "datasourceStates", Map.of(
                                                    "formBased", Map.of(
                                                            "layers", Map.of(
                                                                    "timeline", Map.of(
                                                                            "columns", Map.of(
                                                                                    "time", Map.of(
                                                                                            "params", Map.of("interval", "auto"),
                                                                                            "isBucketed", true,
                                                                                            "operationType", "date_histogram",
                                                                                            "sourceField", "created_at",
                                                                                            "label", "Time",
                                                                                            "dataType", "date"
                                                                                    ),
                                                                                    "kb", Map.of(
                                                                                            "label", "KB",
                                                                                            "dataType", "string",
                                                                                            "operationType", "terms",
                                                                                            "sourceField", "kb_name.keyword",
                                                                                            "isBucketed", true,
                                                                                            "params", Map.of("size", 5, "orderBy", Map.of("type", "column", "columnId", "count"), "orderDirection", "desc")
                                                                                    ),
                                                                                    "count", Map.of(
                                                                                            "label", "Anomaly Count",
                                                                                            "dataType", "number",
                                                                                            "operationType", "count",
                                                                                            "sourceField", "___records___",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of()
                                                                                    )
                                                                            ),
                                                                            "columnOrder", List.of("time", "kb", "count")
                                                                    )
                                                            )
                                                    )
                                            ),
                                            "query", Map.of("query", "", "language", "kuery")
                                    )
                            )
                    ),
                    "gridData", Map.of("x", 0, "y", 14, "w", 24, "h", 12, "i", "6"),
                    "version", "8.19.3"
            );
            panels.add(timeline);
            references.add(Map.of("type", "index-pattern", "id", dataViewId, "name", "6:indexpattern-datasource-layer-timeline"));

            // Panel 7: Anomaly Values Over Time (Line Chart)
            Map<String, Object> valuesChart = Map.of(
                    "type", "lens",
                    "panelIndex", "7",
                    "embeddableConfig", Map.of(
                            "attributes", Map.of(
                                    "title", "📉 Anomaly Values Over Time",
                                    "visualizationType", "lnsXY",
                                    "type", "lens",
                                    "references", List.of(Map.of(
                                            "type", "index-pattern",
                                            "id", dataViewId,
                                            "name", "indexpattern-datasource-layer-values"
                                    )),
                                    "state", Map.of(
                                            "filters", List.of(),
                                            "adHocDataViews", Map.of(),
                                            "visualization", Map.of(
                                                    "title", "",
                                                    "preferredSeriesType", "line",
                                                    "layers", List.of(Map.of(
                                                            "accessors", List.of("avgval", "maxval"),
                                                            "layerType", "data",
                                                            "seriesType", "line",
                                                            "layerId", "values",
                                                            "xAccessor", "time"
                                                    )),
                                                    "legend", Map.of("isVisible", true, "position", "right")
                                            ),
                                            "datasourceStates", Map.of(
                                                    "formBased", Map.of(
                                                            "layers", Map.of(
                                                                    "values", Map.of(
                                                                            "columns", Map.of(
                                                                                    "time", Map.of(
                                                                                            "params", Map.of("interval", "auto"),
                                                                                            "isBucketed", true,
                                                                                            "operationType", "date_histogram",
                                                                                            "sourceField", "created_at",
                                                                                            "label", "Time",
                                                                                            "dataType", "date"
                                                                                    ),
                                                                                    "avgval", Map.of(
                                                                                            "label", "Avg Value",
                                                                                            "dataType", "number",
                                                                                            "operationType", "average",
                                                                                            "sourceField", "value",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of()
                                                                                    ),
                                                                                    "maxval", Map.of(
                                                                                            "label", "Max Value",
                                                                                            "dataType", "number",
                                                                                            "operationType", "max",
                                                                                            "sourceField", "value",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of()
                                                                                    )
                                                                            ),
                                                                            "columnOrder", List.of("time", "avgval", "maxval")
                                                                    )
                                                            )
                                                    )
                                            ),
                                            "query", Map.of("query", "", "language", "kuery")
                                    )
                            )
                    ),
                    "gridData", Map.of("x", 0, "y", 26, "w", 24, "h", 10, "i", "7"),
                    "version", "8.19.3"
            );
            panels.add(valuesChart);
            references.add(Map.of("type", "index-pattern", "id", dataViewId, "name", "7:indexpattern-datasource-layer-values"));

            // Panel 8: Anomalies by Metric (Horizontal Bar)
            Map<String, Object> metricBar = Map.of(
                    "type", "lens",
                    "panelIndex", "8",
                    "embeddableConfig", Map.of(
                            "attributes", Map.of(
                                    "title", "📊 Anomalies by Metric",
                                    "visualizationType", "lnsXY",
                                    "type", "lens",
                                    "references", List.of(Map.of(
                                            "type", "index-pattern",
                                            "id", dataViewId,
                                            "name", "indexpattern-datasource-layer-metricbar"
                                    )),
                                    "state", Map.of(
                                            "filters", List.of(),
                                            "adHocDataViews", Map.of(),
                                            "visualization", Map.of(
                                                    "title", "",
                                                    "preferredSeriesType", "bar_horizontal",
                                                    "layers", List.of(Map.of(
                                                            "accessors", List.of("cnt"),
                                                            "layerType", "data",
                                                            "seriesType", "bar_horizontal",
                                                            "layerId", "metricbar",
                                                            "xAccessor", "metric"
                                                    )),
                                                    "legend", Map.of("isVisible", false)
                                            ),
                                            "datasourceStates", Map.of(
                                                    "formBased", Map.of(
                                                            "layers", Map.of(
                                                                    "metricbar", Map.of(
                                                                            "columns", Map.of(
                                                                                    "metric", Map.of(
                                                                                            "label", "Metric",
                                                                                            "dataType", "string",
                                                                                            "operationType", "terms",
                                                                                            "sourceField", "metric.keyword",
                                                                                            "isBucketed", true,
                                                                                            "params", Map.of("size", 10, "orderBy", Map.of("type", "column", "columnId", "cnt"), "orderDirection", "desc")
                                                                                    ),
                                                                                    "cnt", Map.of(
                                                                                            "label", "Count",
                                                                                            "dataType", "number",
                                                                                            "operationType", "count",
                                                                                            "sourceField", "___records___",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of()
                                                                                    )
                                                                            ),
                                                                            "columnOrder", List.of("metric", "cnt")
                                                                    )
                                                            )
                                                    )
                                            ),
                                            "query", Map.of("query", "", "language", "kuery")
                                    )
                            )
                    ),
                    "gridData", Map.of("x", 24, "y", 20, "w", 12, "h", 8, "i", "8"),
                    "version", "8.19.3"
            );
            panels.add(metricBar);
            references.add(Map.of("type", "index-pattern", "id", dataViewId, "name", "8:indexpattern-datasource-layer-metricbar"));

            // Panel 9: Anomalies by Bucket Key (Horizontal Bar)
            Map<String, Object> bucketBar = Map.of(
                    "type", "lens",
                    "panelIndex", "9",
                    "embeddableConfig", Map.of(
                            "attributes", Map.of(
                                    "title", "🪣 Anomalies by Time Bucket",
                                    "visualizationType", "lnsXY",
                                    "type", "lens",
                                    "references", List.of(Map.of(
                                            "type", "index-pattern",
                                            "id", dataViewId,
                                            "name", "indexpattern-datasource-layer-bucketbar"
                                    )),
                                    "state", Map.of(
                                            "filters", List.of(),
                                            "adHocDataViews", Map.of(),
                                            "visualization", Map.of(
                                                    "title", "",
                                                    "preferredSeriesType", "bar_horizontal",
                                                    "layers", List.of(Map.of(
                                                            "accessors", List.of("cnt"),
                                                            "layerType", "data",
                                                            "seriesType", "bar_horizontal",
                                                            "layerId", "bucketbar",
                                                            "xAccessor", "bucket"
                                                    )),
                                                    "legend", Map.of("isVisible", false)
                                            ),
                                            "datasourceStates", Map.of(
                                                    "formBased", Map.of(
                                                            "layers", Map.of(
                                                                    "bucketbar", Map.of(
                                                                            "columns", Map.of(
                                                                                    "bucket", Map.of(
                                                                                            "label", "Bucket Key",
                                                                                            "dataType", "string",
                                                                                            "operationType", "terms",
                                                                                            "sourceField", "bucket_key.keyword",
                                                                                            "isBucketed", true,
                                                                                            "params", Map.of("size", 10, "orderBy", Map.of("type", "column", "columnId", "cnt"), "orderDirection", "desc")
                                                                                    ),
                                                                                    "cnt", Map.of(
                                                                                            "label", "Count",
                                                                                            "dataType", "number",
                                                                                            "operationType", "count",
                                                                                            "sourceField", "___records___",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of()
                                                                                    )
                                                                            ),
                                                                            "columnOrder", List.of("bucket", "cnt")
                                                                    )
                                                            )
                                                    )
                                            ),
                                            "query", Map.of("query", "", "language", "kuery")
                                    )
                            )
                    ),
                    "gridData", Map.of("x", 36, "y", 20, "w", 12, "h", 8, "i", "9"),
                    "version", "8.19.3"
            );
            panels.add(bucketBar);
            references.add(Map.of("type", "index-pattern", "id", dataViewId, "name", "9:indexpattern-datasource-layer-bucketbar"));

            // Panel 10: Z-Score Distribution Over Time (Heatmap-like bar)
            Map<String, Object> zscoreChart = Map.of(
                    "type", "lens",
                    "panelIndex", "10",
                    "embeddableConfig", Map.of(
                            "attributes", Map.of(
                                    "title", "⚡ Z-Score Severity Over Time",
                                    "visualizationType", "lnsXY",
                                    "type", "lens",
                                    "references", List.of(Map.of(
                                            "type", "index-pattern",
                                            "id", dataViewId,
                                            "name", "indexpattern-datasource-layer-zscore"
                                    )),
                                    "state", Map.of(
                                            "filters", List.of(),
                                            "adHocDataViews", Map.of(),
                                            "visualization", Map.of(
                                                    "title", "",
                                                    "preferredSeriesType", "bar_stacked",
                                                    "layers", List.of(Map.of(
                                                            "accessors", List.of("avgz", "maxz"),
                                                            "layerType", "data",
                                                            "seriesType", "bar_stacked",
                                                            "layerId", "zscore",
                                                            "xAccessor", "time"
                                                    )),
                                                    "legend", Map.of("isVisible", true, "position", "right")
                                            ),
                                            "datasourceStates", Map.of(
                                                    "formBased", Map.of(
                                                            "layers", Map.of(
                                                                    "zscore", Map.of(
                                                                            "columns", Map.of(
                                                                                    "time", Map.of(
                                                                                            "params", Map.of("interval", "auto"),
                                                                                            "isBucketed", true,
                                                                                            "operationType", "date_histogram",
                                                                                            "sourceField", "created_at",
                                                                                            "label", "Time",
                                                                                            "dataType", "date"
                                                                                    ),
                                                                                    "avgz", Map.of(
                                                                                            "label", "Avg Z-Score",
                                                                                            "dataType", "number",
                                                                                            "operationType", "average",
                                                                                            "sourceField", "algorithm_details.z_score",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of()
                                                                                    ),
                                                                                    "maxz", Map.of(
                                                                                            "label", "Max Z-Score",
                                                                                            "dataType", "number",
                                                                                            "operationType", "max",
                                                                                            "sourceField", "algorithm_details.z_score",
                                                                                            "isBucketed", false,
                                                                                            "params", Map.of()
                                                                                    )
                                                                            ),
                                                                            "columnOrder", List.of("time", "avgz", "maxz")
                                                                    )
                                                            )
                                                    )
                                            ),
                                            "query", Map.of("query", "", "language", "kuery")
                                    )
                            )
                    ),
                    "gridData", Map.of("x", 24, "y", 28, "w", 24, "h", 8, "i", "10"),
                    "version", "8.19.3"
            );
            panels.add(zscoreChart);
            references.add(Map.of("type", "index-pattern", "id", dataViewId, "name", "10:indexpattern-datasource-layer-zscore"));

            var body = Map.of(
                    "attributes", Map.of(
                            "title", title,
                            "version", 3,
                            "description", "Comprehensive Anomaly Detection Dashboard - Auto-generated",
                            "timeRestore", false,
                            "controlGroupInput", Map.of(
                                    "chainingSystem", "HIERARCHICAL",
                                    "controlStyle", "oneLine",
                                    "showApplySelections", false,
                                    "ignoreParentSettingsJSON", "{\"ignoreFilters\":false,\"ignoreQuery\":false,\"ignoreTimerange\":false,\"ignoreValidations\":false}",
                                    "panelsJSON", "{}"
                            ),
                            "optionsJSON", "{\"useMargins\":true,\"syncColors\":true,\"syncCursor\":true,\"syncTooltips\":true,\"hidePanelTitles\":false}",
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

            if (resp.statusCode() == 409) {
                System.out.println("Dashboard error conflict board already exists" + resp.statusCode() + ": " + resp.body());
                return null;
            }

            return null;

        } catch (Exception e) {
            throw new RuntimeException("Error creating dashboard with embedded lens", e);
        }
    }

}
