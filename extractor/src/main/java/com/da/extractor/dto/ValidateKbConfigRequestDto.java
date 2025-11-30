package com.da.extractor.dto;

import jakarta.validation.constraints.NotEmpty;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Unified validation request for KB configurations.
 * Validates query, CRON expression, and frequency constraints in a single call.
 */
@NoArgsConstructor
@Getter
@Setter
public class ValidateKbConfigRequestDto {

    /**
     * The Elasticsearch SQL query to validate.
     * Should include $from and $to placeholders for time range substitution.
     */
    @NotEmpty(message = "Query must not be empty")
    private String query;

    /**
     * Query mode: "aggregated" or "raw".
     * Determines minimum frequency requirements and validation behavior.
     */
    @NotEmpty(message = "Query mode must not be empty")
    private String query_mode;

    /**
     * The name of the timestamp field in the query output.
     * Used to validate that the query returns the expected timestamp column.
     */
    @NotEmpty(message = "Timestamp field must not be empty")
    private String timestamp_field;

    /**
     * CRON expression for detection frequency.
     * Supports both 5-field (UNIX) and 6-field (Spring with seconds) formats.
     */
    @NotEmpty(message = "CRON expression must not be empty")
    private String cron_expression;

}
