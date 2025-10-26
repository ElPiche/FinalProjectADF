package com.da.extractor.entity.serie;

import lombok.*;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.Date;


@Data
@NoArgsConstructor
@AllArgsConstructor
@Document(collection = "series")
@Getter
@Setter
public class SeriesElement {

    @Id
    private String id;

    @Field("value")
    private Long value;

    @Field("timestamp")
    private Date timestamp;

    @Field("metadata")
    private Metadata metadata;

}