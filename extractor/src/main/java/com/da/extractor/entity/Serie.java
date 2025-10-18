package com.da.extractor.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.List;
import java.util.Map;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Document(collection = "series")
public class Serie {

    @Id
    private String id;

    @Field("kb_id")
    private String kbId;

    @Field("kb_description")
    private String kbDescription;

    @Field("serie")
    private List<Map<String, Object>> serie;
}
