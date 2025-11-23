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
        try{
            extractorService.extractData(validateQueryRequestDto.getQuery(), data -> {
                if(data == null || data.isEmpty()) {
                    validationErrors.add("No data returned from the query.");
                } else  {
                    if(!data.stream().allMatch(row ->
                            row.containsKey("timestamp") || row.containsKey("es_timestamp"))){
                        validationErrors.add("Missing required timestamp field in the data.");
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
}
