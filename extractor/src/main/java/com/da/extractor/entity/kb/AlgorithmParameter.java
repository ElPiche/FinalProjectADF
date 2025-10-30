package com.da.extractor.entity.kb;

import com.da.extractor.entity.KeyValuePair;
import com.mongodb.lang.Nullable;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.List;

@AllArgsConstructor
@NoArgsConstructor
@Getter
@Setter
public class AlgorithmParameter {

    private String dimension;

    @Field("alg_metadata")
    @Nullable
    private List<KeyValuePair> algMetadata;

}
