package com.da.extractor.controller;

import com.da.extractor.dto.ValidateQueryRequestDto;
import com.da.extractor.dto.ValidateQueryResponseDto;
import com.da.extractor.pipeline.ExtractorService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.List;

@RestController
@RequestMapping("/api/validate")
public class ValidatorController {

    private final ExtractorService extractorService;

    public ValidatorController(ExtractorService extractorService) {
        this.extractorService = extractorService;
    }

    @PostMapping(value = "/query")
    public ResponseEntity<ValidateQueryResponseDto> validateQuery(@RequestBody ValidateQueryRequestDto validateQueryRequestDto) {
        List<String> validationErrors = new ArrayList<>();

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
        }catch (Exception e){
            return ResponseEntity.internalServerError().build();
        }

        if(validationErrors.isEmpty()){
            return ResponseEntity.ok().body(new ValidateQueryResponseDto("Query is valid", null));
        }

        return ResponseEntity.badRequest().body(new ValidateQueryResponseDto("Query validation failed", validationErrors));
    }
}
