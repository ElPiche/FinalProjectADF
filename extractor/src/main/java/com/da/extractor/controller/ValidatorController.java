package com.da.extractor.controller;

import co.elastic.clients.elasticsearch._types.ElasticsearchException;
import com.da.extractor.dto.ValidateQueryRequestDto;
import com.da.extractor.dto.ValidateQueryResponseDto;
import com.da.extractor.pipeline.ExtractorService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@RestController
@RequestMapping("/api/validate")
public class ValidatorController {

    private final ExtractorService extractorService;
    private final Logger logger = LoggerFactory.getLogger(ValidatorController.class.getName());

    public ValidatorController(ExtractorService extractorService) {
        this.extractorService = extractorService;
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
