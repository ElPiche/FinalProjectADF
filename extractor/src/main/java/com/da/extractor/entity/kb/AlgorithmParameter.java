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
    
    // New unified schema adds is_active toggle for each dimension
    @Field("is_active")
    private boolean isActive = true;

    // New unified schema uses "metadata" instead of "alg_metadata"
    @Nullable
    private List<KeyValuePair> metadata;
    
    public boolean isActive() {
        return isActive;
    }

}
