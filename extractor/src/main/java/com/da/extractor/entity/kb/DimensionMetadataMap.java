package com.da.extractor.entity.kb;

import org.springframework.data.mongodb.core.mapping.Field;

import java.util.List;
import java.util.Map;

public class DimensionMetadataMap{
    private String dimension;
    @Field("algorithm_metadata")
    List<Map<String, Object>> algorithmMetadata;
}