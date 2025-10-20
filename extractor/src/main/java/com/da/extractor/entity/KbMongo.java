package com.da.extractor.entity;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.List;
import java.util.Map;

//@AllArgsConstructor
@Getter
@Setter
@NoArgsConstructor
@Document(collection ="testLogsKB")
public class KbMongo {

    @Id
    private String id;
    private KbConfig kbConfig;

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    public static class KbConfig{
        @Field("id")
        private String kbId;
        private String description;
        private Scheduling scheduling;
    }

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Scheduling{
        private TrainingConfig trainingConfig;
        private DetectionConfig detectionConfig;
    }

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    public static class TrainingConfig{
        private String from; //O datetime
        private String to;
        private String window;
        private String mode; //TODO: eliminarlo
        private Boolean isActive;
        private String queryElastic;
    }

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    public static class DetectionConfig{
        private String frequency;
        private int window;
        private String start;
        private String mode; //TODO: eliminarlo
        private Boolean isActive;
        private String queryElastic;
    }

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ADAlgParameters{
        Map<String, List<Object>> algorithmParameters;
//        private Zscore zscore;
//        private Arma arma;
    }
//    No hacen falta porque los parametros son dinamicos
//    public static class Zscore{
//        private List<String> observedValues;
//    }

//    public static class Arma{
//
//        private String observedValue;
//        private double p;
//        private double d;
//        private double q;
//    }

}

