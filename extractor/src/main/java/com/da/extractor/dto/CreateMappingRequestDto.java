package com.da.extractor.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.Setter;

@AllArgsConstructor
@Getter
@Setter
@JsonSerialize
public class CreateMappingRequestDto {

    @JsonProperty("kbId")
    private String kbId;

    @JsonProperty("sourceIndex")
    private String sourceIndex;
}
