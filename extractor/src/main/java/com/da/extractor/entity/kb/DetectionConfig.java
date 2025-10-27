package com.da.extractor.entity.kb;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.Date;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class DetectionConfig{
    @Field("detection_query")
    private String queryElastic;
    @Field("from")
    private Date start;
    private String frequency;
    @Field("detection_window")
    private int window;
    @Field("is_active")
    private boolean isActive;
}