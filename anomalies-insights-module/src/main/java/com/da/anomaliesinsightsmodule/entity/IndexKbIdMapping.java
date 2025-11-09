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

    @Field(name = "indexName")
    private String indexName;

    @Field(name = "dataViewId")
    private String dataViewId;

    @Field(name = "savedSearchId")
    private String savedSearchId;

    @Field(name = "lensId")
    private String lensId;

    @Field(name = "dashboardId")
    private String dashboardId;

}