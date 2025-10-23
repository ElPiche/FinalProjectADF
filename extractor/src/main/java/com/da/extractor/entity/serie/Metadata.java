package com.da.extractor.entity.serie;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.mongodb.core.mapping.Field;

@AllArgsConstructor
@NoArgsConstructor
@Getter
@Setter
public class Metadata {

    @Field("kbId")
    private String kbId;

    @Field("dim")
    private String dim;

    @Field("mode")
    private Mode mode;
}
