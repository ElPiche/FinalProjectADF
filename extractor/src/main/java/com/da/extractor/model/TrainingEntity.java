package com.da.extractor.model;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.List;
import java.util.Map;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class TrainingEntity {

    @Id
    private String id;

    @Field("kb_Id")
    private String kbId;

    @Field("kb_description")
    private String kbDescription;

    private String mode;

    private TrainingAlgorithm algorithm;

    @Field("observed_values")
    private Map<String, List<Values>> observedValues;


    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    public static class TrainingAlgorithm{
        private String name;
        private TrainingAlgorithmParameters parameters;
    }

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    public static class TrainingAlgorithmParameters{

        @Field("train_window")
        private Integer trainWindow;
        private String from;
        private String to;


    }

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Values{
        private String timestamp;
        private Double value;
    }


}


/*
* {
  "training_data": {
    // Example of training data for ZScore algorithm with 5xx status code counter
    "_id": {
      "$oid": "68f3e1e1a856aa9308751164"
    },
    "kb_id": "3af5b1d2-5d4e-4c3b-9f7e-123456789abc",
    "kb_description": "WIP",
    "mode": "train",
    "algorithm": {
      "name": "ZScore",
      "parameters": {
        "train_window": 60,
        "from": "2025-10-01T00:00:00.000Z",
        "to": "2025-11-10T00:00:00.000Z"
      }
    },
    "observed_values": [
      "5xx_status_codes": [
        {"timestamp": "2025-10-01T00:00:00.000Z", "value": 10},
        {"timestamp": "2025-10-01T01:00:00.000Z", "value": 12},
        {"timestamp": "2025-10-01T02:00:00.000Z", "value": 9},
        // ... more hourly data points ...
        {"timestamp": "2025-11-09T23:00:00.000Z", "value": 15}
      ],
      "4xx_status_codes": [
        {"timestamp": "2025-10-01T00:00:00.000Z", "value": 20},
        {"timestamp": "2025-10-01T01:00:00.000Z", "value": 22},
        {"timestamp": "2025-10-01T02:00:00.000Z", "value": 19},
        // ... more hourly data points ...
        {"timestamp": "2025-11-09T23:00:00.000Z", "value": 25}
      ]
    ]
  },
* */