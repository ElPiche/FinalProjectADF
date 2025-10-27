package com.da.extractor.model;

import com.da.extractor.entity.KbMongo;
import com.da.extractor.entity.serie.Mode;
import com.da.extractor.enums.ConfigMode;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@AllArgsConstructor
@NoArgsConstructor
@Builder
public class PipelineConfig {

    String queryElastic;
    private String kbId;
    private String description;
    private Integer window; // en minutos
    private Mode mode;
    KbMongo.ADAlgParameters adAlgParameters;

}
