package com.da.extractor.pipeline;

import com.da.extractor.entity.serie.Mode;
import lombok.AllArgsConstructor;
import lombok.Getter;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.List;

@AllArgsConstructor
@Getter
public class PipeMetadata {

    private String kbId;

    private List<String> observedValues;

    private Mode mode;

    private String timestampField;
}
