package com.da.extractor.entity.training;

import com.da.extractor.entity.KeyValuePair;
import com.da.extractor.entity.kb.DimensionMetadataMap;
import lombok.*;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.Collection;
import java.util.Date;
import java.util.List;
import java.util.Map;

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

    void setObservedValuesFromDimensionMetadataMaps(List<DimensionMetadataMap> dimensionMetadataMaps){
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

        public ObservedValue(DimensionMetadataMap from){
            this.dimension = from.getDimension();
            this.algorithmMetadata = from.getAlgorithmMetadata();
        }
    }

}
