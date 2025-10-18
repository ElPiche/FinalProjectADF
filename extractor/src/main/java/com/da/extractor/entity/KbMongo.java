package com.da.extractor.entity;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

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
        private String queryElastic;
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
        private String mode;
    }

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    public static class DetectionConfig{
        private String frequency;
        private String window;
        private String start;
        private String mode;
    }

    @Getter
    @Setter
    @NoArgsConstructor
    @AllArgsConstructor
    public static class daAlgParameters{
        private Zscore zscore;
        private Arma arma;
    }

    //TODO: Verificar que esten bién los parametros de estos algoritmos.
    public static class Zscore{
        private String observedValue;
        private double threshold;
    }

    public static class Arma{

        private String observedValue;
        private double p;
        private double d;
        private double q;
    }

}

