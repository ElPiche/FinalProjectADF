package com.da.anomaliesinsightsmodule.entity;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Document(indexName = "index_kb_id_mappings")
public class IndexKbIdMapping {

    @Id
    private String kbId;

    // Source index being monitored (e.g., "app-logs") - used for dashboard naming
    @Field(name = "sourceIndex")
    private String sourceIndex;
    
    // Anomaly output index (derived from sourceIndex, e.g., "app-logs_anomalies")
    @Field(name = "anomalyIndex")
    private String anomalyIndex;

    @Field(name = "dataViewId")
    private String dataViewId;

    @Field(name = "savedSearchId")
    private String savedSearchId;

    @Field(name = "dashboardId")
    private String dashboardId;

}