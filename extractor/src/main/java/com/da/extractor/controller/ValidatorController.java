package com.da.extractor.controller;

import co.elastic.clients.elasticsearch._types.ElasticsearchException;
import com.da.extractor.dto.ValidateCronRequestDto;
import com.da.extractor.dto.ValidateCronResponseDto;
import com.da.extractor.dto.ValidateKbConfigRequestDto;
import com.da.extractor.dto.ValidateKbConfigResponseDto;
import com.da.extractor.dto.ValidateQueryRequestDto;
import com.da.extractor.dto.ValidateQueryResponseDto;
import com.da.extractor.pipeline.ExtractorService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.support.CronExpression;
import org.springframework.web.bind.annotation.*;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

@RestController
@RequestMapping("/api/validate")
public class ValidatorController {

    private final ExtractorService extractorService;
    private final Logger logger = LoggerFactory.getLogger(ValidatorController.class.getName());

    /**
     * Minimum detection frequency in seconds by query mode.
     * - raw: 60 seconds (1 minute) - raw queries are heavier
     * - aggregated: 1 second - aggregated queries can run at sub-second granularity
     */
    private static final Map<String, Long> MIN_DETECTION_FREQUENCY_SECONDS = Map.of(
            "raw", 60L,
            "aggregated", 1L
    );
    
    /**
     * Valid query modes.
     */
    private static final Set<String> VALID_QUERY_MODES = Set.of("raw", "aggregated");

    public ValidatorController(ExtractorService extractorService) {
        this.extractorService = extractorService;
    }

    // ============================================================================
    // INDIVIDUAL VALIDATION ENDPOINTS (used by modify_kb_config for point-to-point)
    // ============================================================================

    /**
     * Validates query_mode value.
     * Must be "raw" or "aggregated".
     */
    @PostMapping(value = "/query-mode")
    public ResponseEntity<ValidateKbConfigResponseDto.ValidationResult> validateQueryMode(
            @RequestBody Map<String, String> request) {
        String queryMode = request.get("query_mode");
        
        logger.info("Validating query_mode: {}", queryMode);
        
        ValidateKbConfigResponseDto.ValidationResult result = validateQueryModeInternal(queryMode);
        
        if (result.isValid()) {
            logger.info("query_mode '{}' is valid ✅", queryMode);
            return ResponseEntity.ok(result);
        } else {
            logger.warn("query_mode validation failed: {}", result.getErrors());
            return ResponseEntity.badRequest().body(result);
        }
    }

    /**
     * Validates timestamp_field value.
     * Must be non-empty string.
     */
    @PostMapping(value = "/timestamp-field")
    public ResponseEntity<ValidateKbConfigResponseDto.ValidationResult> validateTimestampField(
            @RequestBody Map<String, String> request) {
        String timestampField = request.get("timestamp_field");
        
        logger.info("Validating timestamp_field: {}", timestampField);
        
        ValidateKbConfigResponseDto.ValidationResult result = validateTimestampFieldInternal(timestampField);
        
        if (result.isValid()) {
            logger.info("timestamp_field '{}' is valid ✅", timestampField);
            return ResponseEntity.ok(result);
        } else {
            logger.warn("timestamp_field validation failed: {}", result.getErrors());
            return ResponseEntity.badRequest().body(result);
        }
    }

    /**
     * Validates Elasticsearch SQL query syntax and optionally checks for timestamp field.
     */
    @PostMapping(value = "/query")
    public ResponseEntity<ValidateQueryResponseDto> validateQuery(@RequestBody ValidateQueryRequestDto request) {
        logger.info("Validating query: {}", request.getQuery());
        
        String timestampField = determineTimestampField(request);
        logger.info("Validating timestamp field: {}", timestampField);
        
        ValidateKbConfigResponseDto.ValidationResult result = validateQueryInternal(request.getQuery(), timestampField);
        
        if (result.isValid()) {
            logger.info("Query validation passed ✅");
            return ResponseEntity.ok().body(new ValidateQueryResponseDto("Query is valid", null));
        } else {
            logger.warn("Query validation failed ❌");
            return ResponseEntity.badRequest().body(new ValidateQueryResponseDto("Query validation failed", result.getErrors()));
        }
    }

    /**
     * Validates a CRON expression and checks if it meets the minimum frequency requirements.
     */
    @PostMapping(value = "/cron")
    public ResponseEntity<ValidateCronResponseDto> validateCron(@RequestBody ValidateCronRequestDto request) {
        String cronExpression = request.getCron_expression();
        String queryMode = request.getQuery_mode();
        
        logger.info("Validating CRON expression: {} for query mode: {}", cronExpression, queryMode);
        
        // Validate query mode first
        ValidateKbConfigResponseDto.ValidationResult queryModeResult = validateQueryModeInternal(queryMode);
        if (!queryModeResult.isValid()) {
            return ResponseEntity.badRequest().body(
                new ValidateCronResponseDto("CRON validation failed", queryModeResult.getErrors(), null)
            );
        }
        
        String normalizedQueryMode = queryMode.trim().toLowerCase();
        CronValidationResult result = validateCronInternal(cronExpression, normalizedQueryMode);
        
        if (result.valid) {
            logger.info("CRON expression valid: {} (interval: {}s) ✅", cronExpression, result.intervalSeconds);
            return ResponseEntity.ok().body(
                new ValidateCronResponseDto("CRON expression is valid", null, result.intervalSeconds)
            );
        } else {
            logger.warn("CRON validation failed: {}", result.errors);
            return ResponseEntity.badRequest().body(
                new ValidateCronResponseDto("CRON validation failed", result.errors, result.intervalSeconds)
            );
        }
    }

    // ============================================================================
    // UNIFIED VALIDATION ENDPOINT (used by create_da_config for bulk validation)
    // ============================================================================

    /**
     * Unified KB configuration validation endpoint.
     * Validates all fields in a single API call by delegating to individual validators.
     * 
     * This is the preferred endpoint for validating new KB configurations as it
     * performs all validations in one round-trip.
     */
    @PostMapping(value = "/kb-config")
    public ResponseEntity<ValidateKbConfigResponseDto> validateKbConfig(@RequestBody ValidateKbConfigRequestDto request) {
        logger.info("Unified KB config validation: query_mode={}, timestamp_field={}, cron={}", 
                request.getQuery_mode(), request.getTimestamp_field(), request.getCron_expression());
        
        List<String> allErrors = new ArrayList<>();
        
        // 1. Validate query_mode (needed for CRON frequency floor)
        ValidateKbConfigResponseDto.ValidationResult queryModeResult = validateQueryModeInternal(request.getQuery_mode());
        if (!queryModeResult.isValid()) {
            allErrors.addAll(queryModeResult.getErrors());
            // Return early - query_mode is needed for other validations
            return ResponseEntity.badRequest().body(ValidateKbConfigResponseDto.builder()
                    .message("KB config validation failed")
                    .valid(false)
                    .queryModeValidation(queryModeResult)
                    .errors(allErrors)
                    .build());
        }
        
        String normalizedQueryMode = request.getQuery_mode().trim().toLowerCase();
        
        // 2. Validate timestamp_field
        ValidateKbConfigResponseDto.ValidationResult timestampFieldResult = 
                validateTimestampFieldInternal(request.getTimestamp_field());
        if (!timestampFieldResult.isValid()) {
            allErrors.addAll(timestampFieldResult.getErrors());
        }
        
        // 3. Validate Query (uses timestamp_field)
        ValidateKbConfigResponseDto.ValidationResult queryResult = validateQueryInternal(
                request.getQuery(), 
                request.getTimestamp_field()
        );
        if (!queryResult.isValid()) {
            allErrors.addAll(queryResult.getErrors());
        }
        
        // 4. Validate CRON and frequency floor (uses query_mode)
        CronValidationResult cronResult = validateCronInternal(
                request.getCron_expression(), 
                normalizedQueryMode
        );
        ValidateKbConfigResponseDto.ValidationResult cronValidation = ValidateKbConfigResponseDto.ValidationResult.builder()
                .valid(cronResult.valid)
                .message(cronResult.valid ? "CRON expression is valid" : "CRON validation failed")
                .errors(cronResult.errors)
                .build();
        if (!cronResult.valid) {
            allErrors.addAll(cronResult.errors);
        }
        
        boolean isValid = allErrors.isEmpty();
        
        ValidateKbConfigResponseDto response = ValidateKbConfigResponseDto.builder()
                .message(isValid ? "KB configuration is valid" : "KB config validation failed")
                .valid(isValid)
                .queryModeValidation(queryModeResult)
                .timestampFieldValidation(timestampFieldResult)
                .queryValidation(queryResult)
                .cronValidation(cronValidation)
                .cronIntervalSeconds(cronResult.intervalSeconds)
                .errors(isValid ? null : allErrors)
                .build();
        
        if (isValid) {
            logger.info("KB config validation passed ✅");
            return ResponseEntity.ok(response);
        } else {
            logger.info("KB config validation failed with {} errors ❌", allErrors.size());
            return ResponseEntity.badRequest().body(response);
        }
    }

    // ============================================================================
    // INTERNAL VALIDATION METHODS (shared by all endpoints - NO DUPLICATION)
    // ============================================================================

    /**
     * Internal query_mode validation logic.
     */
    private ValidateKbConfigResponseDto.ValidationResult validateQueryModeInternal(String queryMode) {
        List<String> errors = new ArrayList<>();
        
        if (queryMode == null || queryMode.isBlank()) {
            errors.add("Query mode must not be empty");
            return ValidateKbConfigResponseDto.ValidationResult.builder()
                    .valid(false)
                    .message("Query mode validation failed")
                    .errors(errors)
                    .build();
        }
        
        String normalized = queryMode.trim().toLowerCase();
        if (!VALID_QUERY_MODES.contains(normalized)) {
            errors.add("Invalid query mode '" + queryMode + "'. Must be 'raw' or 'aggregated'");
            return ValidateKbConfigResponseDto.ValidationResult.builder()
                    .valid(false)
                    .message("Query mode validation failed")
                    .errors(errors)
                    .build();
        }
        
        return ValidateKbConfigResponseDto.ValidationResult.builder()
                .valid(true)
                .message("Query mode is valid")
                .errors(null)
                .build();
    }

    /**
     * Internal timestamp_field validation logic.
     */
    private ValidateKbConfigResponseDto.ValidationResult validateTimestampFieldInternal(String timestampField) {
        List<String> errors = new ArrayList<>();
        
        if (timestampField == null || timestampField.isBlank()) {
            errors.add("Timestamp field must not be empty");
            return ValidateKbConfigResponseDto.ValidationResult.builder()
                    .valid(false)
                    .message("Timestamp field validation failed")
                    .errors(errors)
                    .build();
        }
        
        // Check for leading/trailing whitespace (reject before trimming)
        if (!timestampField.equals(timestampField.trim())) {
            errors.add("Timestamp field cannot have leading or trailing whitespace: '" + timestampField + "'");
            return ValidateKbConfigResponseDto.ValidationResult.builder()
                    .valid(false)
                    .message("Timestamp field validation failed")
                    .errors(errors)
                    .build();
        }
        
        // Check for spaces within the field name
        if (timestampField.contains(" ")) {
            errors.add("Timestamp field cannot contain spaces: '" + timestampField + "'");
            return ValidateKbConfigResponseDto.ValidationResult.builder()
                    .valid(false)
                    .message("Timestamp field validation failed")
                    .errors(errors)
                    .build();
        }
        
        return ValidateKbConfigResponseDto.ValidationResult.builder()
                .valid(true)
                .message("Timestamp field is valid")
                .errors(null)
                .build();
    }

    /**
     * Internal query validation logic (reusable by both /query and /kb-config endpoints).
     */
    private ValidateKbConfigResponseDto.ValidationResult validateQueryInternal(String query, String timestampField) {
        List<String> errors = new ArrayList<>();
        
        if (query == null || query.isBlank()) {
            errors.add("Query must not be empty");
            return ValidateKbConfigResponseDto.ValidationResult.builder()
                    .valid(false)
                    .message("Query validation failed")
                    .errors(errors)
                    .build();
        }
        
        if (timestampField == null || timestampField.isBlank()) {
            timestampField = "es_timestamp"; // fallback for legacy compatibility
        }
        
        final String finalTimestampField = timestampField;
        
        try {
            extractorService.extractData(query, data -> {
                if (data == null || data.isEmpty()) {
                    errors.add("No data returned from the query.");
                } else {
                    if (!data.stream().allMatch(row -> row.containsKey(finalTimestampField))) {
                        errors.add("Missing required timestamp field '" + finalTimestampField + "' in the data.");
                    }
                }
            });
        } catch (ElasticsearchException e) {
            logger.warn("Query validation Elasticsearch error", e);
            errors.add("The query does not conform to Elasticsearch SQL syntax: " + e.getMessage());
        } catch (Exception e) {
            logger.error("Query validation unexpected error", e);
            errors.add("Query validation failed with unexpected error: " + e.getMessage());
        }
        
        return ValidateKbConfigResponseDto.ValidationResult.builder()
                .valid(errors.isEmpty())
                .message(errors.isEmpty() ? "Query is valid" : "Query validation failed")
                .errors(errors.isEmpty() ? null : errors)
                .build();
    }
    
    /**
     * Internal CRON validation logic (reusable by both /cron and /kb-config endpoints).
     */
    private CronValidationResult validateCronInternal(String cronExpression, String normalizedQueryMode) {
        CronValidationResult result = new CronValidationResult();
        result.errors = new ArrayList<>();
        
        if (cronExpression == null || cronExpression.isBlank()) {
            result.errors.add("CRON expression must not be empty");
            return result;
        }
        
        String springCron = normalizeCron(cronExpression.trim());
        
        try {
            CronExpression cron = CronExpression.parse(springCron);
            
            LocalDateTime now = LocalDateTime.now();
            LocalDateTime next1 = cron.next(now);
            if (next1 == null) {
                result.errors.add("CRON expression never fires");
                return result;
            }
            
            LocalDateTime next2 = cron.next(next1);
            if (next2 == null) {
                result.errors.add("CRON expression only fires once");
                return result;
            }
            
            result.intervalSeconds = Duration.between(next1, next2).getSeconds();
            long minimumSeconds = MIN_DETECTION_FREQUENCY_SECONDS.get(normalizedQueryMode);
            
            if (result.intervalSeconds < minimumSeconds) {
                result.errors.add(String.format(
                    "Detection frequency '%s' executes every %d seconds, which is faster than the minimum %d seconds allowed for query_mode '%s'",
                    cronExpression, result.intervalSeconds, minimumSeconds, normalizedQueryMode
                ));
                return result;
            }
            
            result.valid = true;
            
        } catch (IllegalArgumentException e) {
            result.errors.add("Invalid CRON expression: " + e.getMessage());
        }
        
        return result;
    }

    // ============================================================================
    // HELPER METHODS
    // ============================================================================

    /**
     * Determines which timestamp field to validate based on request parameters.
     */
    private String determineTimestampField(ValidateQueryRequestDto request) {
        if (request.getTimestamp_field() != null && !request.getTimestamp_field().isBlank()) {
            return request.getTimestamp_field();
        }
        return "es_timestamp";
    }
    
    /**
     * Normalizes a CRON expression to 6-field Spring format.
     */
    private String normalizeCron(String cron) {
        String[] parts = cron.trim().split("\\s+");
        return (parts.length == 5) ? "0 " + cron : cron;
    }
    
    /**
     * Internal helper class for CRON validation results.
     */
    private static class CronValidationResult {
        boolean valid = false;
        List<String> errors;
        Long intervalSeconds;
    }
}
