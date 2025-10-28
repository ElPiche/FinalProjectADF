package com.da.extractor.entity.training;

import com.da.extractor.entity.kb.KbMongo;
import com.da.extractor.entity.serie.Mode;
import lombok.*;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

@Document(collection = "trainingconfig")
@NoArgsConstructor
@AllArgsConstructor
@Getter
@Setter
@Builder
public class TrainConfig {

    @Id
    private String id;

    @Field("kb_id")
    private String kbId;

    @Field("kb_description")
    private String kbDescription;

    @Field("created_at")
    private Date createdAt;

    private short mode;

    private List<AlgorithmConfig> algorithms;

    public TrainConfig(KbMongo from){
        this.kbId = from.getId();
        this.kbDescription = from.getDescription();
        this.createdAt = Date.from(Instant.now());
        this.mode = (short) Mode.TRAINING.ordinal();
        this.algorithms = new ArrayList<>();
        
        var trainingConfig = from.getScheduling().getTrainingConfig();

        from.getAdAlgParameters().getKvpParams().forEach((algorithmName , dimMetadata) -> {
            var algorithm = new AlgorithmConfig();
            algorithm.setName(algorithmName);

            var algorithmParameters = AlgorithmParameters.builder()
                    .trainWindow(trainingConfig.getWindow())
                    .from(Date.from(Instant.parse(trainingConfig.getFrom())))
                    .to(Date.from(Instant.parse(trainingConfig.getTo())))
                    .build();

            algorithmParameters.setObservedValuesFromDimensionMetadataMaps(dimMetadata);
            algorithm.setParameters(algorithmParameters);

            this.algorithms.add(algorithm);
        });
    }
    
}
