package com.da.extractor.entity.kb;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.Collection;
import java.util.List;

//@AllArgsConstructor
@Getter
@Setter
@NoArgsConstructor
@Document(collection ="kb_configs")
public class KbMongo{

    @Id
    private String id;
    private String name;
    private String description;
    @Field("change_flag")
    private short changeFlag;
    private Scheduling scheduling;
    
    // New unified schema uses singular "algorithm" instead of "algorithms" array
    private Algorithm algorithm;
    
    // Optional: bucket profile reference for context-aware detection
    @Field("bucket_profile_id")
    private String bucketProfileId;
    
    // Query mode metadata
    @Field("query_mode")
    private QueryMode queryMode;
    
    // Unified SQL query for both training and detection
    @Field("elasticsearch_sql_query")
    private String elasticsearchSqlQuery;

    public List<String> getObservedValues(){
        if (algorithm == null || algorithm.getParameters() == null) {
            return List.of();
        }
        return algorithm.getParameters().stream()
                .filter(AlgorithmParameter::isActive)
                .map(AlgorithmParameter::getDimension)
                .distinct()
                .toList();
    }
}