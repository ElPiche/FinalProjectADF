package com.da.anomaliesinsightsmodule.repository;

import com.da.anomaliesinsightsmodule.entity.IndexKbIdMapping;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

import java.util.Optional;

public interface IndexKbIdMappingRepo extends ElasticsearchRepository<IndexKbIdMapping, String> {
    Optional<IndexKbIdMapping> findByKbId(String kbId);
    Optional<IndexKbIdMapping> findByIndexName(String indexName);
}