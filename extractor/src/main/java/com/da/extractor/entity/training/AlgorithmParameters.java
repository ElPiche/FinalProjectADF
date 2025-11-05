package com.da.extractor.entity.training;

import com.da.extractor.entity.KeyValuePair;
import com.da.extractor.entity.kb.AlgorithmParameter;
import com.mongodb.lang.Nullable;
import jakarta.validation.constraints.Null;
import lombok.*;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;

@NoArgsConstructor
@AllArgsConstructor
@Getter
@Setter
@Builder
public class AlgorithmParameters {

    @Field("train_window")
    private int trainWindow;

    @Field("observed_values")
    private List<ObservedValue> observedValues;

    private Date from;

    private Date to;

    void setObservedValuesFromDimensionMetadataMaps(List<AlgorithmParameter> dimensionMetadataMaps){
        this.observedValues = dimensionMetadataMaps.stream()
                .map(ObservedValue::new)
                .toList();
    }

    @AllArgsConstructor
    @NoArgsConstructor
    @Getter
    public static class ObservedValue {
        private String dimension;

        @Field("algorithm_metadata")
        private List<KeyValuePair> algorithmMetadata;

        public ObservedValue(AlgorithmParameter from){
            this.dimension = from.getDimension();
            this.algorithmMetadata = from.getAlgMetadata() != null ? from.getAlgMetadata() : new ArrayList<>();
        }
    }
}
