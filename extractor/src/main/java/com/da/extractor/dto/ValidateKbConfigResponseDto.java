package com.da.extractor.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.List;

/**
 * Unified validation response for KB configurations.
 * Contains validation results for all fields: query_mode, timestamp_field, query, and CRON.
 */
@NoArgsConstructor
@AllArgsConstructor
@Builder
@Getter
@Setter
public class ValidateKbConfigResponseDto {

    /**
     * Overall validation status message.
     */
    private String message;

    /**
     * Whether the entire configuration is valid.
     */
    private boolean valid;

    /**
     * Query mode validation result.
     */
    private ValidationResult queryModeValidation;

    /**
     * Timestamp field validation result.
     */
    private ValidationResult timestampFieldValidation;

    /**
     * Query validation result.
     */
    private ValidationResult queryValidation;

    /**
     * CRON expression validation result.
     */
    private ValidationResult cronValidation;

    /**
     * The interval in seconds between consecutive CRON executions.
     * Null if CRON validation failed.
     */
    private Long cronIntervalSeconds;

    /**
     * Combined list of all validation errors.
     */
    private List<String> errors;

    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    @Getter
    @Setter
    public static class ValidationResult {
        private boolean valid;
        private String message;
        private List<String> errors;
    }

}
