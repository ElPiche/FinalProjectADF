package com.da.extractor.entity.kb;

import com.da.extractor.entity.training.AlgorithmConfig;
import com.da.extractor.entity.training.AlgorithmParameters;
import com.da.extractor.entity.training.TrainConfig;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;
import org.springframework.data.mongodb.core.mapping.Field;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Map;

//@AllArgsConstructor
@Getter
@Setter
@NoArgsConstructor
@Document(collection ="kb_configs")
public class KbMongo{

    @Id
    private String id;
    private String name;
    private String description;
    @Field("change_flag")
    private short changeFlag;
    private Scheduling scheduling;
    @Field("ad_alg_parameters")
    private ADAlgParameters adAlgParameters;

}