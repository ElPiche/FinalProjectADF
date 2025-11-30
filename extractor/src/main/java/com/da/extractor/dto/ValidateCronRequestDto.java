package com.da.extractor.dto;

import jakarta.validation.constraints.NotEmpty;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@NoArgsConstructor
@Getter
@Setter
public class ValidateCronRequestDto {

    @NotEmpty(message = "CRON expression must not be empty")
    private String cron_expression;

    /**
     * Query mode: "aggregated" or "raw".
     * Used to determine minimum frequency requirements.
     * - raw: minimum 60 seconds between executions
     * - aggregated: minimum 10 seconds between executions
     */
    @NotEmpty(message = "Query mode must not be empty")
    private String query_mode;

}
