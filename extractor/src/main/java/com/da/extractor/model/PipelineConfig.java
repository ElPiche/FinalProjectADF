package com.da.extractor.model;

import com.da.extractor.entity.KbMongo;
import com.da.extractor.enums.ConfigMode;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@AllArgsConstructor
@NoArgsConstructor
public class PipelineConfig {

    String queryElastic;
    private String kbId;
    private String description;
    private int window; // en minutos
    private ConfigMode mode;
    KbMongo.ADAlgParameters adAlgParameters;

}
