package com.da.anomaliesinsightsmodule.service;
import co.elastic.clients.elasticsearch._types.ElasticsearchException;
import co.elastic.clients.elasticsearch.core.IndexResponse;
import com.da.anomaliesinsightsmodule.dto.DocumentDto;
import com.da.anomaliesinsightsmodule.entity.IndexKbIdMapping;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import java.time.Instant;
import java.util.Locale;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;


@Service
public class InsightsService {

    private final ElasticsearchService elasticsearchService;

    private final KibanaService kibanaService;

    private final EmailNotificationService emailNotificationService;

    private final Logger logger = LoggerFactory.getLogger(InsightsService.class);

    public InsightsService(ElasticsearchService elasticsearchService, KibanaService kibanaService, EmailNotificationService emailNotificationService) {
        this.elasticsearchService = elasticsearchService;
        this.kibanaService = kibanaService;
        this.emailNotificationService = emailNotificationService;
    }

    public void createKbMapping(IndexKbIdMapping kbIdMapping) throws Exception {

        //Normalizar nombre.
        String normalizedIndexName = normalizeIndexName(kbIdMapping.getIndexName());

        kbIdMapping.setIndexName(normalizedIndexName);

        if(!elasticsearchService.indexExists(normalizedIndexName)){

            //Crear indice
            elasticsearchService.createIndex(normalizedIndexName);
            logger.info("Creating anomalies index in elasticsearch: " + normalizedIndexName);

            //Crear dataview
            String dataViewId = kibanaService.createDataView(normalizedIndexName);

            logger.info("Creating dataView for index:  " + normalizedIndexName + " data view id: " + dataViewId);

            //Crear saved search + lens para dashboard
            String ssId = kibanaService.createSavedSearch(dataViewId, "SavedSearch - " + normalizedIndexName);

            logger.info("Creating saved search:  " + ssId + " data view id: " + dataViewId);

            //Crear dashboard
            String dashId = kibanaService.createDashboardWithEmbeddedLens("Dashboard - " + normalizedIndexName, dataViewId, ssId);

            logger.info("Creating dashboard:  " + dashId + " saved search id: " + ssId);

            //Cargar mapping
            kbIdMapping.setDataViewId(dataViewId);
            kbIdMapping.setSavedSearchId(ssId);
            kbIdMapping.setDashboardId(dashId);

        }

        //Crear mapeo
        elasticsearchService.createKbMapping(kbIdMapping);

        logger.info("Creating mapping:  kbid: " + kbIdMapping.getKbId() + " Index name: " + normalizedIndexName);

    }

    public IndexResponse uploadDocument(String kbId, DocumentDto doc) throws Exception {

        //Obtener nombre de indice atraves de mapeo
        Optional<IndexKbIdMapping> mappingOpt = elasticsearchService.getKbIdMapping(kbId);

        IndexKbIdMapping mapping = mappingOpt
                .orElseThrow(() -> new NoSuchElementException("kb mapping not found: " + kbId));

        IndexResponse response;

        //Subir documento.
        response = elasticsearchService.indexAnomalyDocument(mapping.getIndexName(), doc);
        logger.info("Inserting document in index:  " + mapping.getIndexName());

        //Refrescar dataView
        if (mapping.getDataViewId() != null) {

            kibanaService.refreshDataViewFields(mapping.getDataViewId());
            logger.info("Refreshing Data view fields: " + mapping.getDataViewId());

        }

        if(doc.getEmail() != null) {
            sendAnomalyEmail(doc, mapping);
        }

        return response;
    }

    public void sendAnomalyEmail(DocumentDto doc, IndexKbIdMapping mapping) throws Exception {

        try{

            emailNotificationService.sendHtmlEmailFromTemplate(
                    doc.getEmail(),   // o recorrer lista
                    "Anomalía detectada en configuración:" + doc.getKbName(),
                    "templates/anomaly-email.html",
                    Map.of(
                            "kbName", doc.getKbName(),
                            "anomalyMetric", doc.getMetric(),
                            "anomalyValue", doc.getValue().toString(),
                            "anomalyTimestamp", doc.getTimestamp(),
                            "resultsIndexName", mapping.getIndexName(),
                            "kibanaUrl", "http://localhost:5602/app/dashboards#/view/" + mapping.getDashboardId()
                    )
            );

        }catch(Exception e){
            logger.error("Error while sending anomaly email:" + e.getMessage());
            //throw e;
        }
    }
    public void sendMailTest(String to) throws Exception {

        var kbName = "test";

        var anomalyMetric = "httpcodes";

        var anomalyValue = "muchos values";

        var timestamp = Instant.now();

        var indexName = "nombre facha";

        var kibanaId = "70a44f12-a013-47ba-96ee-e046aa8b00c9";

        emailNotificationService.sendHtmlEmailFromTemplate(
                to,   // o recorrer lista
                "Anomalía detectada en KB: test"  ,//kb.getName(),
                "templates/anomaly-email.html",
                Map.of(
                        "kbName", kbName,
                        "anomalyMetric", anomalyMetric,
                        "anomalyValue", anomalyValue.toString(),
                        "anomalyTimestamp", timestamp.toString(),
                        "resultsIndexName", indexName,
                        "kibanaUrl", "http://localhost:5602/app/dashboards#/view/" + kibanaId
                )
        );
    }

    private String normalizeIndexName(String rawName) {
        if (rawName == null || rawName.isBlank()) {
            throw new IllegalArgumentException("Index name cannot be null or empty");
        }

        // a) minúsculas
        String normalized = rawName.toLowerCase(Locale.ROOT);

        // b) reemplazar espacios y separadores peligrosos por guion
        normalized = normalized.replaceAll("[\\s,:*?\"<>|/\\\\]+", "-");

        // c) quitar caracteres no permitidos (solo a-z0-9-_)
        normalized = normalized.replaceAll("[^a-z0-9-_]", "");

        // d) evitar prefijos reservados
        if (normalized.startsWith("-") || normalized.startsWith("+") || normalized.startsWith("_")) {
            normalized = "idx" + normalized;
        }

        // e) evitar nombres reservados
        if (normalized.equals(".") || normalized.equals("..")) {
            normalized = "idx-" + normalized;
        }

        // f) agregar sufijo _anomalies_result si no lo tiene
        if (!normalized.endsWith("_anomalies_result")) {
            normalized = normalized + "_anomalies_result";
        }

        // g) limitar longitud
        if (normalized.length() > 255) {
            normalized = normalized.substring(0, 255);
        }

        return normalized;
    }

}
