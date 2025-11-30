package com.da.extractor.entity.kb;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.mongodb.core.mapping.Field;

/**
 * Query mode metadata for unified SQL queries.
 * Specifies how the query results should be interpreted.
 */
@AllArgsConstructor
@NoArgsConstructor
@Getter
@Setter
public class QueryMode {

    /**
     * Data extraction mode: "raw" or "aggregated".
     * - raw: Individual events returned
     * - aggregated: GROUP BY output with aggregations
     */
    private String type;

    /**
     * The timestamp field name in the query output.
     * This field must be present in the SQL SELECT clause.
     */
    @Field("timestamp_field")
    private String timestampField;

}
