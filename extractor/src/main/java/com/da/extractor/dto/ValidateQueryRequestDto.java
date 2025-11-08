package com.da.extractor.dto;

import jakarta.validation.constraints.NotEmpty;
import lombok.Getter;
import lombok.NoArgsConstructor;

@NoArgsConstructor
@Getter
public class ValidateQueryRequestDto {

    @NotEmpty(message = "Query must not be empty")
    private String query;

}
