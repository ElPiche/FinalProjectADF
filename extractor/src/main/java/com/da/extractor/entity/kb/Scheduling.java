package com.da.extractor.entity.kb;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.mongodb.core.mapping.Field;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class Scheduling{
    @Field("training_config")
    private TrainingConfig trainingConfig;
    @Field("detection_config")
    private DetectionConfig detectionConfig;
}