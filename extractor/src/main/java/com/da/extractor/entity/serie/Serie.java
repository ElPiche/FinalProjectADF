package com.da.extractor.entity.serie;

import co.elastic.clients.util.DateTime;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.query.Meta;


@Data
@NoArgsConstructor
@AllArgsConstructor
@Document(collection = "series")
public class Serie {

    @Id
    private String id;

    @Field("value")
    private int value;

    @Field("timestamp")
    private DateTime timestamp;

    @Field("metadata")
    private Metadata metadata;

}