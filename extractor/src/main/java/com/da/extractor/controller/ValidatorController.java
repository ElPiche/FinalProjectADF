package com.da.extractor.controller;

import co.elastic.clients.elasticsearch._types.ElasticsearchException;
import com.da.extractor.dto.ValidateQueryRequestDto;
import com.da.extractor.dto.ValidateQueryResponseDto;
import com.da.extractor.dto.ValidateCronRequestDto;
import com.da.extractor.dto.ValidateCronResponseDto;
import com.da.extractor.pipeline.ExtractorService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.support.CronExpression;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/validate")
public class ValidatorController {

    private final ExtractorService extractorService;
    private final Logger logger = LoggerFactory.getLogger(ValidatorController.class.getName());
    
    // Minimum detection frequencies in seconds per query mode
    private static final Map<String, Long> MIN_DETECTION_FREQUENCY_SECONDS = Map.of(
        "raw", 60L,
        "aggregated", 10L
    );

    public ValidatorController(ExtractorService extractorService) {
        this.extractorService = extractorService;
    }

    @PostMapping(value = "/cron")
    public ResponseEntity<ValidateCronResponseDto> validateCron(@RequestBody ValidateCronRequestDto request) {
        String cronExpression = request.getCronExpression();
        String queryModeType = request.getQueryModeType() != null ? request.getQueryModeType().toLowerCase() : "raw";
        
        logger.info("Validating CRON expression: {} for query mode: {}", cronExpression, queryModeType);
        
        try {
            // Normalize to 6-field format if needed
            String normalizedCron = normalizeCron(cronExpression);
            
            // Parse with Spring's CronExpression (supports 6-field with seconds)
            CronExpression cron = CronExpression.parse(normalizedCron);
            
            // Calculate interval between first two executions
            LocalDateTime now = LocalDateTime.now();
            LocalDateTime next1 = cron.next(now);
            LocalDateTime next2 = cron.next(next1);
            
            if (next1 == null || next2 == null) {
                return ResponseEntity.badRequest().body(
                    new ValidateCronResponseDto(false, "CRON expression does not produce valid next executions", null, normalizedCron)
                );
            }
            
            long intervalSeconds = Duration.between(next1, next2).getSeconds();
            
            // Check minimum frequency for query mode
            Long minSeconds = MIN_DETECTION_FREQUENCY_SECONDS.getOrDefault(queryModeType, 60L);
            if (intervalSeconds < minSeconds) {
                String message = String.format(
                    "CRON '%s' executes every %d seconds, which is faster than the minimum %d seconds allowed for query_mode '%s'",
                    cronExpression, intervalSeconds, minSeconds, queryModeType
                );
                logger.warn(message);
                return ResponseEntity.badRequest().body(
                    new ValidateCronResponseDto(false, message, intervalSeconds, normalizedCron)
                );
            }
            
            logger.info("CRON validation successful: {} -> interval {}s", normalizedCron, intervalSeconds);
            return ResponseEntity.ok().body(
                new ValidateCronResponseDto(true, "CRON expression is valid", intervalSeconds, normalizedCron)
            );
            
        } catch (IllegalArgumentException e) {
            logger.warn("Invalid CRON expression '{}': {}", cronExpression, e.getMessage());
            return ResponseEntity.badRequest().body(
                new ValidateCronResponseDto(false, "Invalid CRON expression: " + e.getMessage(), null, null)
            );
        }
    }
    
    /**
     * Normalizes a CRON expression to 6-field format (with seconds).
     * If 5 fields are provided, prepends "0" for seconds.
     */
    private String normalizeCron(String cron) {
        String[] parts = cron.trim().split("\\s+");
        return (parts.length == 5) ? "0 " + cron : cron;
    }

    @PostMapping(value = "/query")
    public ResponseEntity<ValidateQueryResponseDto> validateQuery(@RequestBody ValidateQueryRequestDto validateQueryRequestDto) {
        List<String> validationErrors = new ArrayList<>();

        logger.info("Iniciando validacion de query: {}", validateQueryRequestDto.getQuery());
        
        // Determine which timestamp field to look for
        final String timestampField = determineTimestampField(validateQueryRequestDto);
        logger.info("Validating timestamp field: {}", timestampField);
        
        try{
            extractorService.extractData(validateQueryRequestDto.getQuery(), data -> {
                if(data == null || data.isEmpty()) {
                    validationErrors.add("No data returned from the query.");
                } else  {
                    // Check if the specified timestamp field exists in the data
                    if(!data.stream().allMatch(row -> row.containsKey(timestampField))){
                        validationErrors.add("Missing required timestamp field '" + timestampField + "' in the data.");
                    }
                }
            });
        }catch (ElasticsearchException e){
            logger.warn("Validacion arrojo error de Elastic", e);
            validationErrors.add("The query does not conform to Elasticsearch SQL syntax");

        }catch (Exception e){
            logger.error("Validacion arrojo error inesperado", e);
            return ResponseEntity.internalServerError().build();
        }

        if(validationErrors.isEmpty()){
            logger.info("Validacion de query sin errores");
            logger.info("{} ✅", validateQueryRequestDto.getQuery());
            return ResponseEntity.ok().body(new ValidateQueryResponseDto("Query is valid", null));
        }

        logger.info("Validacion de query con errores");
        logger.info("{} ❌", validateQueryRequestDto.getQuery());
        return ResponseEntity.badRequest().body(new ValidateQueryResponseDto("Query validation failed", validationErrors));
    }

    /**
     * Determines which timestamp field to validate based on request parameters.
     * If timestamp_field is provided, use it directly.
     * Otherwise, fall back to legacy behavior (check for "timestamp" or "es_timestamp").
     */
    private String determineTimestampField(ValidateQueryRequestDto request) {
        // If timestamp_field is explicitly provided, use it
        if (request.getTimestamp_field() != null && !request.getTimestamp_field().isBlank()) {
            return request.getTimestamp_field();
        }
        // Legacy fallback - try es_timestamp first (common convention)
        return "es_timestamp";
    }
}
