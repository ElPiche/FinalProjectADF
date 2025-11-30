package com.da.extractor.dto;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.util.List;

@NoArgsConstructor
@AllArgsConstructor
@Getter
@Setter
public class ValidateCronResponseDto {

    private String message;
    private List<String> errors;
    
    /**
     * The interval in seconds between consecutive CRON executions.
     * Useful for the caller to understand the effective detection frequency.
     */
    private Long intervalSeconds;

}
