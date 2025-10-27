package com.da.extractor.entity.training;

import com.da.extractor.entity.serie.Mode;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

import java.util.Date;

@Document(collection = "trainingconfig")
@NoArgsConstructor
@AllArgsConstructor
@Getter
@Setter
public class TrainConfig {

    @Id
    private String id;

    private String kbId;

    private String kbDescription;

    private Date createdAt;

    private short mode;

    private AlgorithmConfig algorithm;
    
}
