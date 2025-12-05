package com.da.anomaliesinsightsmodule.repository;

import com.da.anomaliesinsightsmodule.entity.IndexKbIdMapping;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface IndexKbIdMappingRepo extends ElasticsearchRepository<IndexKbIdMapping, String> {
    Optional<IndexKbIdMapping> findByKbId(String kbId);

    Optional<IndexKbIdMapping> findBySourceIndex(String sourceIndex);
}