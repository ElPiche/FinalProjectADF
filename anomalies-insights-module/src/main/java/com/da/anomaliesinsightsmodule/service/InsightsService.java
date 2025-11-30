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

    private final EmailRateLimiterService emailRateLimiterService;

    private final Logger logger = LoggerFactory.getLogger(InsightsService.class);

    public InsightsService(ElasticsearchService elasticsearchService, KibanaService kibanaService, 
                           EmailNotificationService emailNotificationService,
                           EmailRateLimiterService emailRateLimiterService) {
        this.elasticsearchService = elasticsearchService;
        this.kibanaService = kibanaService;
        this.emailNotificationService = emailNotificationService;
        this.emailRateLimiterService = emailRateLimiterService;
    }

    public void createKbMapping(IndexKbIdMapping kbIdMapping) throws Exception {

        // Source index (e.g., "app-logs") - used for dashboard naming
        String sourceIndex = kbIdMapping.getSourceIndex();
        
        // Derive anomaly output index from source (e.g., "app-logs" -> "app-logs_anomalies")
        String anomalyIndex = sanitizeIndexName(sourceIndex) + "_anomalies";
        kbIdMapping.setAnomalyIndex(anomalyIndex);

        if(!elasticsearchService.indexExists(anomalyIndex)){

            //Crear indice for anomalies
            elasticsearchService.createIndex(anomalyIndex);
            logger.info("Creating anomalies index in elasticsearch: " + anomalyIndex);

            //Crear dataview
            String dataViewId = kibanaService.createDataView(anomalyIndex);

            logger.info("Creating dataView for index:  " + anomalyIndex + " data view id: " + dataViewId);

            //Crear saved search + lens para dashboard - use SOURCE index for title
            String ssId = kibanaService.createSavedSearch(dataViewId, "SavedSearch - " + sourceIndex);

            logger.info("Creating saved search:  " + ssId + " data view id: " + dataViewId);

            //Crear dashboard - use SOURCE index for title (what we're monitoring)
            String dashId = kibanaService.createDashboardWithEmbeddedLens("Dashboard - " + sourceIndex, dataViewId, ssId);

            logger.info("Creating dashboard:  " + dashId + " saved search id: " + ssId);

            //Cargar mapping
            kbIdMapping.setDataViewId(dataViewId);
            kbIdMapping.setSavedSearchId(ssId);
            kbIdMapping.setDashboardId(dashId);

        }

        //Crear mapeo
        elasticsearchService.createKbMapping(kbIdMapping);

        logger.info("Creating mapping:  kbid: " + kbIdMapping.getKbId() + " Source index: " + sourceIndex + " Anomaly index: " + anomalyIndex);

    }

    public IndexResponse uploadDocument(String kbId, DocumentDto doc) throws Exception {

        //Obtener nombre de indice atraves de mapeo
        Optional<IndexKbIdMapping> mappingOpt = elasticsearchService.getKbIdMapping(kbId);

        IndexKbIdMapping mapping = mappingOpt
                .orElseThrow(() -> new NoSuchElementException("kb mapping not found: " + kbId));

        IndexResponse response;

        //Subir documento to anomaly index
        response = elasticsearchService.indexAnomalyDocument(mapping.getAnomalyIndex(), doc);
        logger.info("Inserting document in index:  " + mapping.getAnomalyIndex());

        //Refrescar dataView
        if (mapping.getDataViewId() != null) {

            kibanaService.refreshDataViewFields(mapping.getDataViewId());
            logger.info("Refreshing Data view fields: " + mapping.getDataViewId());

        }

        // Email notification logging
        logger.info("================== EMAIL NOTIFICATION CHECK ==================");
        logger.info("Document received - kbId: {}, metric: {}, email field: '{}'", 
                kbId, doc.getMetric(), doc.getEmail());
        
        if(doc.getEmail() != null && !doc.getEmail().isBlank()) {
            // Support multiple emails separated by commas
            String[] emails = doc.getEmail().split(",");
            logger.info("Email field is present, {} recipient(s) found: {}", emails.length, doc.getEmail());
            for (String email : emails) {
                String trimmedEmail = email.trim();
                if (!trimmedEmail.isBlank()) {
                    logger.info("Sending email to: {}", trimmedEmail);
                    sendAnomalyEmailToRecipient(doc, mapping, trimmedEmail);
                }
            }
        } else {
            logger.warn("No email configured in document - email field is null or empty. Skipping email notification.");
        }
        logger.info("==============================================================");

        return response;
    }

    public void sendAnomalyEmail(DocumentDto doc, IndexKbIdMapping mapping) throws Exception {
        // Legacy method - sends to the email in the document
        if (doc.getEmail() != null && !doc.getEmail().isBlank()) {
            sendAnomalyEmailToRecipient(doc, mapping, doc.getEmail());
        }
    }

    public void sendAnomalyEmailToRecipient(DocumentDto doc, IndexKbIdMapping mapping, String recipientEmail) throws Exception {

        logger.info(">>> sendAnomalyEmailToRecipient called for email: {}", recipientEmail);
        
        try{
            // Check rate limit before sending
            logger.info("Checking rate limit for email: {}", recipientEmail);
            if (!emailRateLimiterService.canSendEmail(recipientEmail)) {
                logger.info("Email to {} rate limited. Status: {}", 
                        recipientEmail, 
                        emailRateLimiterService.getRateLimitStatus(recipientEmail));
                return;
            }

            logger.info("Rate limit check passed. Preparing email template...");
            logger.info("Template variables - kbName: {}, metric: {}, value: {}, timestamp: {}, sourceIndex: {}", 
                    doc.getKbName(), doc.getMetric(), doc.getValue(), doc.getTimestamp(), mapping.getSourceIndex());

            emailNotificationService.sendHtmlEmailFromTemplate(
                    recipientEmail,
                    "Anomalía detectada en configuración:" + doc.getKbName(),
                    "templates/anomaly-email.html",
                    Map.of(
                            "kbName", doc.getKbName(),
                            "anomalyMetric", doc.getMetric(),
                            "anomalyValue", doc.getValue().toString(),
                            "anomalyTimestamp", doc.getTimestamp(),
                            "sourceIndex", mapping.getSourceIndex(),
                            "kibanaUrl", "http://localhost:5602/app/dashboards#/view/" + mapping.getDashboardId()
                    )
            );

            // Record successful send for rate limiting
            emailRateLimiterService.recordEmailSent(recipientEmail);

            logger.info("SUCCESS: Anomaly email sent to: {}", recipientEmail);

        }catch(Exception e){
            logger.error("FAILED: Error while sending anomaly email to {}: {}", recipientEmail, e.getMessage());
            logger.error("Full stack trace:", e);
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

    /**
     * Sanitize an index name for Elasticsearch without adding any suffix.
     * Used for preparing source index names before appending _anomalies.
     */
    private String sanitizeIndexName(String rawName) {
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

        // f) limitar longitud (leave room for _anomalies suffix)
        if (normalized.length() > 245) {
            normalized = normalized.substring(0, 245);
        }

        return normalized;
    }

}
