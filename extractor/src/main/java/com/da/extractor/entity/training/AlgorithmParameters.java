package com.da.extractor.entity.training;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.Date;
import java.util.List;
import java.util.Map;

@NoArgsConstructor
@AllArgsConstructor
@Getter
@Setter
public class AlgorithmParameters {

    @Field("train_window")
    private int trainWindow;

    @Field("observed_values")
    private List<ObservedValue> observedValues;

    private Date from;

    private Date to;


    private static class ObservedValue {
        private String dimension;

        @Field("algorithm_metadata")
        private List<Map<String, Object>> algorithmMetadata;
    }

}
