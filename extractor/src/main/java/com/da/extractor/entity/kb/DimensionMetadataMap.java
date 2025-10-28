package com.da.extractor.entity.kb;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.List;
import java.util.Map;

@NoArgsConstructor
@AllArgsConstructor
@Getter
public class DimensionMetadataMap{
    private String dimension;
    @Field("algorithm_metadata")
    List<Map<String, Object>> algorithmMetadata;
}