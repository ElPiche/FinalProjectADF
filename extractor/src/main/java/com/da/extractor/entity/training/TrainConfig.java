package com.da.extractor.entity.training;

import com.da.extractor.entity.kb.AnomalyConfig;
import com.da.extractor.entity.kb.KbMongo;
import com.da.extractor.entity.serie.Mode;
import lombok.*;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

@Document(collection = "training_config")
@NoArgsConstructor
@AllArgsConstructor
@Getter
@Setter
@Builder
public class TrainConfig {

    @Id
    private String id;

    @Field("kb_id")
    @Indexed(unique = true)
    private String kbId;

    @Field("kb_description")
    private String kbDescription;

    @Field("created_at")
    private Date createdAt;

    @Field("is_trained")
    private boolean isTrained = false;

    private short mode;

    private List<AlgorithmConfig> algorithms;
    
    @Field("anomaly_config")
    private AnomalyConfig anomalyConfig;

    public TrainConfig(KbMongo from){
        this.kbId = from.getId();
        this.kbDescription = from.getDescription();
        this.createdAt = Date.from(Instant.now());
        this.isTrained = false;
        this.mode = (short) Mode.TRAINING.ordinal();
        this.algorithms = new ArrayList<>();
        this.anomalyConfig = from.getAnomalyConfig(); // Copy anomaly notification config
        
        var trainingConfig = from.getScheduling().getTrainingConfig();

        // New unified schema uses singular "algorithm" instead of "algorithms" array
        var algorithmConfig = from.getAlgorithm();
        if (algorithmConfig != null) {
            var algorithm = new AlgorithmConfig();
            algorithm.setName(algorithmConfig.getName());

            // Handle null training_window (legacy field, not used in new unified schema)
            Integer trainWindow = trainingConfig.getWindow();
            if (trainWindow == null) {
                trainWindow = 0;  // Default value for new schema configs
            }

            var algorithmParameters = AlgorithmParameters.builder()
                    .trainWindow(trainWindow)
                    .from(Date.from(Instant.parse(trainingConfig.getFrom())))
                    .to(Date.from(Instant.parse(trainingConfig.getTo())))
                    .build();

            algorithmParameters.setObservedValuesFromDimensionMetadataMaps(algorithmConfig.getParameters());
            algorithm.setParameters(algorithmParameters);

            this.algorithms.add(algorithm);
        }
    }
}
