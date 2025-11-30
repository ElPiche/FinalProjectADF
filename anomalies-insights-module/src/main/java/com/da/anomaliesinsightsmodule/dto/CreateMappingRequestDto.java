package com.da.anomaliesinsightsmodule.dto;

import jakarta.validation.constraints.NotEmpty;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@NoArgsConstructor
@Getter
@Setter
public class CreateMappingRequestDto {

    @NotEmpty(message = "kbId is required")
    private String kbId;

    @NotEmpty(message = "sourceIndex is required")
    private String sourceIndex;

}
