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
public class TrainingConfig{
    @Field("training_query")
    private String queryElastic;
    private String from;
    private String to;
    @Field("training_window")
    private Integer window;
    @Field("is_active")
    private Boolean isActive;
}
