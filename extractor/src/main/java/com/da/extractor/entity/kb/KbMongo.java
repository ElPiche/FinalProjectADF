package com.da.extractor.entity.kb;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.Collection;
import java.util.List;

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
    private List<Algorithm> algorithms;

    public List<String> getObservedValues(){
        return algorithms.stream()
                .flatMap(algorithm -> algorithm.getAlgParameters()
                        .stream()
                        .map(AlgorithmParameter::getDimension)
                )
                .toList();
    }

}