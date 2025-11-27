package com.da.extractor.dto;

import lombok.Data;

@Data
public class ValidateCronRequestDto {
    private String cronExpression;
    private String queryModeType;  // "raw" or "aggregated"
}
