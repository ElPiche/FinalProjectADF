package com.da.anomaliesinsightsmodule.service;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.ElasticsearchException;
import co.elastic.clients.elasticsearch._types.OpType;
import co.elastic.clients.elasticsearch.core.IndexResponse;
import co.elastic.clients.elasticsearch.sql.ElasticsearchSqlClient;
import co.elastic.clients.json.JsonpMapper;
import com.da.anomaliesinsightsmodule.dto.DocumentDto;
import com.da.anomaliesinsightsmodule.entity.IndexKbIdMapping;
import com.da.anomaliesinsightsmodule.repository.IndexKbIdMappingRepo;
import org.apache.commons.codec.digest.DigestUtils;
import org.elasticsearch.client.ResponseException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;


@Service
public class ElasticsearchService {

    final ElasticsearchClient client;

    final JsonpMapper jsonpMapper;

    final ElasticsearchSqlClient sqlClient;

    final IndexKbIdMappingRepo indexKbIdMappingRepo;

    private final Logger logger = LoggerFactory.getLogger(InsightsService.class);

    public ElasticsearchService(ElasticsearchClient client, JsonpMapper jsonpMapper, IndexKbIdMappingRepo indexKbIdMappingRepo) {
        this.client = client;
        this.jsonpMapper = jsonpMapper;
        this.sqlClient = client.sql();
        this.indexKbIdMappingRepo = indexKbIdMappingRepo;
    }

    public IndexResponse createKbMapping(IndexKbIdMapping kbIdMapping) throws Exception {

        if (indexKbIdMappingRepo.findByKbId(kbIdMapping.getKbId()).isPresent()) {
            throw new IllegalArgumentException("Index conflict mapping already exists");
        }

        return client.index(i -> i
                .index("index_kb_id_mappings")
                .id(kbIdMapping.getKbId())
                .opType(OpType.Create)
                .document(kbIdMapping)
        );
    }

    public IndexResponse indexAnomalyDocument(String indexName, String kbId, DocumentDto doc) throws Exception {

        Map<String, Object> docMap = toDocumentMap(doc);

        String documentId = generateDocumentId(kbId, doc);

        logger.info("Generating documentId: " + documentId);

        try {
            return client.index(i -> i
                    .index(indexName)
                    .id(documentId)
                    .opType(OpType.Create)
                    .document(docMap)
            );
        } catch (ElasticsearchException e) {
            if (e.status() == 409) {
                throw new IllegalArgumentException("Document conflict: a document with the same ID already exists in index '" + indexName + "'.", e);
            }
            throw new Exception("Error indexing anomaly document", e);

        } catch (ResponseException e) {
            int status = e.getResponse().getStatusLine().getStatusCode();
            if (status == 409) {
                throw new IllegalArgumentException("Duplicate anomaly (doc already exists). docId=" + documentId, e);
            }
            throw new Exception("Elasticsearch ResponseException (" + status + ")", e);
        }

    }

    public Optional<IndexKbIdMapping> getKbIdMapping(String kbId) throws Exception {
        return indexKbIdMappingRepo.findByKbId(kbId);
    }

    public Optional<IndexKbIdMapping> getKbMappingBySourceIndex(String sourceIndex) throws Exception {
        return indexKbIdMappingRepo.findBySourceIndex(sourceIndex);
    }

    public void createIndex(String indexName) throws Exception {
        client.indices().create(c -> c.index(indexName));
    }

    public boolean indexExists(String indexName) throws IOException {
        return client.indices().exists(e -> e.index(indexName)).value();
    }

    private Map<String, Object> toDocumentMap(DocumentDto dto) {
        Map<String, Object> m = new HashMap<>();

        // Core fields
        if (dto.algorithm != null) m.put("algorithm", dto.algorithm);
        if (dto.metric != null)    m.put("metric", dto.metric);
        if (dto.text != null)      m.put("text", dto.text);
        if (dto.value != null)     m.put("value", dto.value);
        if (dto.email != null)     m.put("email", dto.email);
        if (dto.kbName != null)     m.put("kbName", dto.kbName);

        // KB identification
        if (dto.kbName != null)   m.put("kbName", dto.kbName);

        // Bucket context fields
        if (dto.bucket_key != null)        m.put("bucket_key", dto.bucket_key);
        if (dto.bucket_profile_id != null) m.put("bucket_profile_id", dto.bucket_profile_id);

        // Algorithm-specific details (flexible map - supports any algorithm)
        if (dto.algorithm_details != null) {
            m.put("algorithm_details", dto.algorithm_details);
        }

        // timestamp (si no viene, now())
        String ts = (dto.timestamp != null) ? dto.timestamp : Instant.now().toString();
        // validar parseo básico
        try { Instant.parse(ts); } catch (DateTimeParseException e) { ts = Instant.now().toString(); }

        m.put("timestamp", ts);
        m.put("@timestamp", ts);  // recomendado por Kibana

        // created_at (si no viene, now())
        String created = (dto.created_at != null) ? dto.created_at : Instant.now().toString();
        try { Instant.parse(created); } catch (DateTimeParseException e) { created = Instant.now().toString(); }
        m.put("created_at", created);

        return m;
    }

    private String generateDocumentId(String kbId, DocumentDto doc) {

        requireNonBlank(kbId, "kbId");
        requireNonBlank(doc.algorithm, "algorithm");
        requireNonBlank(doc.metric, "metric");
        requireNonBlank(doc.timestamp, "timestamp");
        requireValidDouble(doc.value, "value");

        String rawKey = String.join("|",
                kbId.trim(),
                doc.algorithm.trim(),
                doc.metric.trim(),
                doc.timestamp.trim(),
                normalizeDouble(doc.value)
        );

        return DigestUtils.sha256Hex(rawKey);
    }

    private void requireNonBlank(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new NullPointerException(
                    "Invalid anomaly document: required field '" + fieldName + "' is null or blank"
            );
        }
    }

    private String normalizeDouble(Double value) {

        return BigDecimal.valueOf(value)
                .setScale(4, RoundingMode.HALF_UP)
                .toPlainString();
    }

    private void requireValidDouble(Double value, String fieldName) {
        if (value == null) {
            throw new NullPointerException(
                    "Invalid anomaly document: required field '" + fieldName + "' is null"
            );
        }
        if (value.isNaN() || value.isInfinite()) {
            throw new IllegalArgumentException(
                    "Invalid anomaly document: field '" + fieldName + "' is NaN or Infinite"
            );
        }
    }
}
