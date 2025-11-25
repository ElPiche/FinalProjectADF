package com.da.extractor.dto;

import jakarta.validation.constraints.NotEmpty;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@NoArgsConstructor
@Getter
@Setter
public class ValidateQueryRequestDto {

    @NotEmpty(message = "Query must not be empty")
    private String query;

    /**
     * Query mode: "aggregated" or "raw".
     * When provided, validation uses the specified timestamp_field.
     */
    private String query_mode;

    /**
     * The name of the timestamp field in the query output.
     * Required when query_mode is specified.
     */
    private String timestamp_field;

}
