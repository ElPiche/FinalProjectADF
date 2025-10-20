package com.da.extractor.model;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.List;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class DetectionModel {


    @Id
    private String id;

    @Field("kb_id")
    private String kbId;

    private String mode;

    private DetectionAlgorithm algorithm;

    private List<Integer> observedValues;

    private static class DetectionAlgorithm{
        private String name;
        private Integer counting;
        private DetectionAlgorithmParameters parameters;
    }

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    private static class DetectionAlgorithmParameters{
        private String from;
        private String to;
    }
}

/*
*
* {
  "_id": {
    "$oid": "68f3e1e1a856aa9308751164"
  },
  "kb_id": "3af5b1d2-5d4e-4c3b-9f7e-123456789abc",
  "mode": "detect",
  "algorithm": {
    "name": "ZScore",
    "counting": "5xx_status_codes",
    "parameters": {
      "from": "2025-11-10T01:00:00.000Z",
      "to": "2025-11-10T02:00:00.000Z"
    }
  },
  "observed_values": [25] // dataframe
//    "observed_value":  // agrupado por hora

}
* */