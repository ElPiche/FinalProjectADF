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
import org.springframework.stereotype.Service;

import java.io.IOException;
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

    public IndexResponse indexAnomalyDocument(String indexName, DocumentDto doc) throws Exception {

        Map<String, Object> docMap = toDocumentMap(doc);

        try {
            return client.index(i -> i
                    .index(indexName)
                    .document(docMap)
            );
        } catch (ElasticsearchException e) {
            //Nunca se debería de dar, dto no tiene id de documento
            if (e.status() == 409) {
                throw new IllegalArgumentException("Document conflict: a document with the same ID already exists in index '" + indexName + "'.", e);
            }
            throw new Exception(e.getMessage());
        }

    }

    public Optional<IndexKbIdMapping> getKbIdMapping(String kbId) throws Exception {
        return indexKbIdMappingRepo.findByKbId(kbId);
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
}
