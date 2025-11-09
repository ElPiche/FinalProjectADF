package com.da.anomaliesinsightsmodule.service;

import co.elastic.clients.elasticsearch.core.IndexResponse;
import com.da.anomaliesinsightsmodule.dto.DocumentDto;
import com.da.anomaliesinsightsmodule.entity.IndexKbIdMapping;
//import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

<<<<<<< Updated upstream
=======
import java.time.Instant;
import java.util.Locale;
import java.util.Map;
>>>>>>> Stashed changes
import java.util.Optional;


@Service
public class InsightsService {

    private final ElasticsearchService elasticsearchService;

    private final KibanaService kibanaService;

    public InsightsService(ElasticsearchService elasticsearchService, KibanaService kibanaService) {
        this.elasticsearchService = elasticsearchService;
        this.kibanaService = kibanaService;
    }

    public void createKbMapping(IndexKbIdMapping kbIdMapping) throws Exception {

<<<<<<< Updated upstream
=======
        //Normalizar nombre.
        String normalizedIndexName = normalizeIndexName(kbIdMapping.getIndexName());
        kbIdMapping.setIndexName(normalizedIndexName);

        //Crear indice
        elasticsearchService.createIndex(normalizedIndexName);

        //Doc test
        Instant now = Instant.now();

        DocumentDto testDoc = new DocumentDto(
                "ZScore",                      // algorithm
                "ASD",                         // metric
                "ASD",                         // text
                now.toString(),                // timestamp
                213.0,                         // value -> NUMÉRICO ✅
                now.toString()                 // created_at
        );

        // Insertar doc de prueba en el índice
        elasticsearchService.indexAnomalyDocument(normalizedIndexName, testDoc);

        //Crear dataview
        String dataViewId = kibanaService.createDataView(normalizedIndexName);

        //Crear saved search + lens para dashboard
        String ssId = kibanaService.createSavedSearch(dataViewId, "SavedSearch - " + normalizedIndexName);
        String lensId = kibanaService.createLensBasic(dataViewId, "Lens - " + normalizedIndexName);

        //Crear dashboard
        String dashId = kibanaService.createDashboardDirect("Dashboard - " + normalizedIndexName, ssId, lensId);

        //Cargar mapping
        kbIdMapping.setDataViewId(dataViewId);
        kbIdMapping.setSavedSearchId(ssId);
        kbIdMapping.setLensId(lensId);
        kbIdMapping.setDashboardId(dashId);

>>>>>>> Stashed changes
        //Crear mapeo
        elasticsearchService.createKbMapping(kbIdMapping);

        //crear indice
        elasticsearchService.createIndex(kbIdMapping.getIndexName());

        //crear dataview
        kibanaService.createDataView(kbIdMapping.getIndexName());

    }

    public IndexResponse uploadDocument(String kbId, DocumentDto doc) throws Exception {

        //Obtener nombre de indice atraves de mapeo
        Optional<IndexKbIdMapping> mappingOpt = elasticsearchService.getKbIdMapping(kbId);

        IndexKbIdMapping mapping = mappingOpt
                .orElseThrow(() -> new IllegalStateException("kb mapping not found: " + kbId));

<<<<<<< Updated upstream
        //subir documento.
        return elasticsearchService.indexAnomalyDocument(mapping.getIndexName(), doc);
=======
        //Subir documento.
        var response = elasticsearchService.indexAnomalyDocument(mapping.getIndexName(), doc);

        //Refrescar dataView
        if (mapping.getDataViewId() != null) {
            kibanaService.refreshDataViewFields(mapping.getDataViewId());
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
>>>>>>> Stashed changes
    }

}
