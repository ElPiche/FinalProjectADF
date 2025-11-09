package com.da.extractor.entity.training;

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

    @Field("index_name")
    private String indexName;

    private short mode;

    private List<AlgorithmConfig> algorithms;

    public TrainConfig(KbMongo from){
        this.kbId = from.getId();
        this.kbDescription = from.getDescription();
        this.createdAt = Date.from(Instant.now());
        this.isTrained = false;
        this.mode = (short) Mode.TRAINING.ordinal();
        this.algorithms = new ArrayList<>();
        
        var trainingConfig = from.getScheduling().getTrainingConfig();

        from.getAlgorithms().forEach((algorithmConfig) -> {
            var algorithm = new AlgorithmConfig();
            algorithm.setName(algorithmConfig.getAlgName());

            var algorithmParameters = AlgorithmParameters.builder()
                    .trainWindow(trainingConfig.getWindow())
                    .from(Date.from(Instant.parse(trainingConfig.getFrom())))
                    .to(Date.from(Instant.parse(trainingConfig.getTo())))
                    .build();

            algorithmParameters.setObservedValuesFromDimensionMetadataMaps(algorithmConfig.getAlgParameters());
            algorithm.setParameters(algorithmParameters);

            this.algorithms.add(algorithm);
        });
    }
}
