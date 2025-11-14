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
import java.util.NoSuchElementException;
import java.util.Optional;


@Service
public class InsightsService {

    private final ElasticsearchService elasticsearchService;

    private final KibanaService kibanaService;

    private final Logger logger = LoggerFactory.getLogger(InsightsService.class);

    public InsightsService(ElasticsearchService elasticsearchService, KibanaService kibanaService) {
        this.elasticsearchService = elasticsearchService;
        this.kibanaService = kibanaService;
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

        try {
            //Crear mapeo
            elasticsearchService.createKbMapping(kbIdMapping);

        } catch (ElasticsearchException e) {

            if (e.status() == 409) {
                //No suchElement es para 404, pero nos salva las papas por ahora
                throw new NoSuchElementException("Conflict, index already exists: " + kbIdMapping.getKbId());
            }

            throw e;
        }

        logger.info("Creating mapping:  kbid: " + kbIdMapping.getKbId() + " Index name: " + normalizedIndexName);

    }

    public IndexResponse uploadDocument(String kbId, DocumentDto doc) throws Exception {

        //Obtener nombre de indice atraves de mapeo
        Optional<IndexKbIdMapping> mappingOpt = elasticsearchService.getKbIdMapping(kbId);

        IndexKbIdMapping mapping = mappingOpt
                .orElseThrow(() -> new NoSuchElementException("kb mapping not found: " + kbId));

        IndexResponse response;

        try {
            //Subir documento.
            response = elasticsearchService.indexAnomalyDocument(mapping.getIndexName(), doc);
            logger.info("Inserting document in index:  " + mapping.getIndexName());

        } catch (ElasticsearchException e) {

            if (e.status() == 409) {
                //No suchElement es para 404, pero nos salva las papas por ahora
                throw new IllegalArgumentException("Conflict, docuement already exists: " + kbId);
            }

            throw e;
        }

        //Refrescar dataView
        if (mapping.getDataViewId() != null) {

            kibanaService.refreshDataViewFields(mapping.getDataViewId());
            logger.info("Refreshing Data view fields: " + mapping.getDataViewId());

        }

        return response;
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
