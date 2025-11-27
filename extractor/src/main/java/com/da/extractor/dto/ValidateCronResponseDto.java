package com.da.extractor.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class ValidateCronResponseDto {
    private boolean valid;
    private String message;
    private Long intervalSeconds;  // Calculated interval between executions
    private String normalizedCron; // The 6-field CRON used by Spring
}
