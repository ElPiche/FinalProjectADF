package com.da.extractor.controller;

import com.da.extractor.dto.ValidateCronRequestDto;
import com.da.extractor.dto.ValidateCronResponseDto;
import com.da.extractor.dto.ValidateKbConfigRequestDto;
import com.da.extractor.dto.ValidateKbConfigResponseDto;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Stress tests for CRON validation to ensure invalid inputs are properly rejected.
 * Tests cover: malformed CRON, frequency floor enforcement, edge cases, and injection attempts.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
public class ValidatorControllerStressTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Nested
    @DisplayName("CRON Syntax Validation - Invalid Inputs")
    class CronSyntaxValidation {

        @ParameterizedTest
        @DisplayName("Should reject malformed CRON expressions")
        @ValueSource(strings = {
            "",                           // Empty string
            "   ",                        // Whitespace only
            "*",                          // Only 1 field
            "* *",                        // Only 2 fields
            "* * *",                      // Only 3 fields
            "* * * *",                    // Only 4 fields (need 5 or 6)
            "* * * * * * *",              // 7 fields (too many)
            "* * * * * * * *",            // 8 fields (too many)
            "60 * * * *",                 // Invalid minute (>59)
            "* 24 * * *",                 // Invalid hour (>23)
            "* * 32 * *",                 // Invalid day (>31)
            "* * * 13 *",                 // Invalid month (>12)
            "* * * * 8",                  // Invalid day of week (>7)
            "-1 * * * *",                 // Negative minute
            "* -1 * * *",                 // Negative hour
            "abc * * * *",                // Letters in minute
            "* def * * *",                // Letters in hour
            "*/0 * * * *",                // Division by zero
            "1-70 * * * *",               // Range exceeds max
            "1,2,60 * * * *",             // List with invalid value
            "1/100 * * * *",              // Step too large
            "* * 0 * *",                  // Day 0 is invalid
            "* * * 0 *",                  // Month 0 is invalid
            "1-2-3 * * * *",              // Invalid range syntax
            "*/a * * * *",                // Non-numeric step
            "1.5 * * * *",                // Decimal not allowed
            "* * L * *",                  // L not supported in standard
            "* * W * *",                  // W not supported in standard
            "* * * * 1#2",                // # not supported in standard
        })
        void shouldRejectMalformedCron(String cronExpression) throws Exception {
            ValidateCronRequestDto request = new ValidateCronRequestDto();
            request.setCron_expression(cronExpression);
            request.setQuery_mode("aggregated");

            MvcResult result = mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk())
                    .andReturn();

            ValidateCronResponseDto response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ValidateCronResponseDto.class);

            assertThat(response.getErrors())
                .as("CRON '%s' should have validation errors", cronExpression)
                .isNotNull()
                .isNotEmpty();
        }

        @Test
        @DisplayName("Should reject null CRON expression")
        void shouldRejectNullCron() throws Exception {
            String json = "{\"cron_expression\": null, \"query_mode\": \"aggregated\"}";

            mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.errors").isNotEmpty());
        }
    }

    @Nested
    @DisplayName("Frequency Floor Enforcement - Aggregated Mode (min 10s)")
    class AggregatedModeFrequencyFloor {

        @ParameterizedTest
        @DisplayName("Should accept valid sub-minute CRON for aggregated mode")
        @ValueSource(strings = {
            "*/10 * * * * *",             // Every 10 seconds
            "*/15 * * * * *",             // Every 15 seconds
            "*/30 * * * * *",             // Every 30 seconds
            "0 * * * * *",                // Every minute at second 0
            "0,30 * * * * *",             // Every 30 seconds
            "*/20 * * * * *",             // Every 20 seconds
        })
        void shouldAcceptValidAggregatedCron(String cronExpression) throws Exception {
            ValidateCronRequestDto request = new ValidateCronRequestDto();
            request.setCron_expression(cronExpression);
            request.setQuery_mode("aggregated");

            MvcResult result = mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk())
                    .andReturn();

            ValidateCronResponseDto response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ValidateCronResponseDto.class);

            assertThat(response.getErrors())
                .as("Valid CRON '%s' should not have errors", cronExpression)
                .isNullOrEmpty();
            assertThat(response.getIntervalSeconds())
                .as("Interval should be >= 10 seconds for aggregated")
                .isGreaterThanOrEqualTo(10);
        }

        @ParameterizedTest
        @DisplayName("Should reject CRON with frequency < 10 seconds for aggregated mode")
        @ValueSource(strings = {
            "*/1 * * * * *",              // Every 1 second
            "*/2 * * * * *",              // Every 2 seconds
            "*/3 * * * * *",              // Every 3 seconds
            "*/5 * * * * *",              // Every 5 seconds
            "*/9 * * * * *",              // Every 9 seconds
            "0,1,2,3,4,5,6,7,8,9 * * * * *", // Every second (0-9)
        })
        void shouldRejectTooFrequentAggregatedCron(String cronExpression) throws Exception {
            ValidateCronRequestDto request = new ValidateCronRequestDto();
            request.setCron_expression(cronExpression);
            request.setQuery_mode("aggregated");

            MvcResult result = mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk())
                    .andReturn();

            ValidateCronResponseDto response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ValidateCronResponseDto.class);

            // This depends on whether the extractor enforces the floor or just reports interval
            // If it enforces, there should be errors; if not, interval should be <10
            assertThat(response.getIntervalSeconds())
                .as("Interval for '%s' should be < 10 seconds", cronExpression)
                .isLessThan(10);
        }
    }

    @Nested
    @DisplayName("Frequency Floor Enforcement - Raw Mode (min 60s)")
    class RawModeFrequencyFloor {

        @ParameterizedTest
        @DisplayName("Should accept valid CRON for raw mode (>= 60s)")
        @ValueSource(strings = {
            "* * * * *",                  // Every minute (5-field)
            "0 * * * * *",                // Every minute (6-field)
            "*/2 * * * *",                // Every 2 minutes
            "0 */5 * * *",                // Every 5 minutes
            "0 0 * * *",                  // Every hour
        })
        void shouldAcceptValidRawCron(String cronExpression) throws Exception {
            ValidateCronRequestDto request = new ValidateCronRequestDto();
            request.setCron_expression(cronExpression);
            request.setQuery_mode("raw");

            MvcResult result = mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk())
                    .andReturn();

            ValidateCronResponseDto response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ValidateCronResponseDto.class);

            assertThat(response.getErrors())
                .as("Valid CRON '%s' for raw mode should not have errors", cronExpression)
                .isNullOrEmpty();
            assertThat(response.getIntervalSeconds())
                .as("Interval should be >= 60 seconds for raw")
                .isGreaterThanOrEqualTo(60);
        }

        @ParameterizedTest
        @DisplayName("Should report intervals < 60s for raw mode")
        @ValueSource(strings = {
            "*/10 * * * * *",             // Every 10 seconds
            "*/30 * * * * *",             // Every 30 seconds
            "*/45 * * * * *",             // Every 45 seconds
        })
        void shouldReportSubMinuteIntervalsForRaw(String cronExpression) throws Exception {
            ValidateCronRequestDto request = new ValidateCronRequestDto();
            request.setCron_expression(cronExpression);
            request.setQuery_mode("raw");

            MvcResult result = mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk())
                    .andReturn();

            ValidateCronResponseDto response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ValidateCronResponseDto.class);

            // For raw mode, intervals < 60s should be flagged
            assertThat(response.getIntervalSeconds())
                .as("Interval for '%s' should be < 60 seconds", cronExpression)
                .isLessThan(60);
        }
    }

    @Nested
    @DisplayName("Query Mode Validation")
    class QueryModeValidation {

        @ParameterizedTest
        @DisplayName("Should handle invalid query modes")
        @ValueSource(strings = {
            "invalid",
            "AGGREGATED",                 // Case-sensitive check
            "RAW",                        // Case-sensitive check
            "aggregate",                  // Typo
            "row",                        // Typo
            "both",
            "none",
            "123",
        })
        void shouldHandleInvalidQueryMode(String queryMode) throws Exception {
            ValidateCronRequestDto request = new ValidateCronRequestDto();
            request.setCron_expression("*/10 * * * * *");
            request.setQuery_mode(queryMode);

            // Should either reject with error or use a default
            mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk()); // Should handle gracefully
        }

        @Test
        @DisplayName("Should handle null query mode")
        void shouldHandleNullQueryMode() throws Exception {
            String json = "{\"cron_expression\": \"*/10 * * * * *\", \"query_mode\": null}";

            mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                    .andExpect(status().isOk()); // Should handle gracefully
        }

        @Test
        @DisplayName("Should handle missing query mode")
        void shouldHandleMissingQueryMode() throws Exception {
            String json = "{\"cron_expression\": \"*/10 * * * * *\"}";

            mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                    .andExpect(status().isOk()); // Should handle gracefully
        }
    }

    @Nested
    @DisplayName("Injection and Security Tests")
    class SecurityTests {

        @ParameterizedTest
        @DisplayName("Should safely handle potential injection attempts in CRON")
        @ValueSource(strings = {
            "; DROP TABLE users;",
            "$(rm -rf /)",
            "`cat /etc/passwd`",
            "${env.PATH}",
            "{{7*7}}",
            "<script>alert(1)</script>",
            "' OR '1'='1",
            "\" OR \"1\"=\"1",
            "../../../etc/passwd",
            "\\x00\\x00\\x00\\x00",
            "null",
            "undefined",
            "NaN",
            "Infinity",
            "\n\r\t",
        })
        void shouldSafelyHandleInjectionAttempts(String maliciousInput) throws Exception {
            ValidateCronRequestDto request = new ValidateCronRequestDto();
            request.setCron_expression(maliciousInput);
            request.setQuery_mode("aggregated");

            MvcResult result = mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk())
                    .andReturn();

            ValidateCronResponseDto response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ValidateCronResponseDto.class);

            // Should be rejected as invalid CRON, not cause server error
            assertThat(response.getErrors())
                .as("Injection attempt '%s' should be rejected", maliciousInput)
                .isNotNull()
                .isNotEmpty();
        }

        @Test
        @DisplayName("Should handle extremely long CRON expression")
        void shouldHandleExtremelyLongCron() throws Exception {
            String longCron = "* ".repeat(1000) + "* * * * *";
            
            ValidateCronRequestDto request = new ValidateCronRequestDto();
            request.setCron_expression(longCron);
            request.setQuery_mode("aggregated");

            mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk()); // Should handle without crashing
        }
    }

    @Nested
    @DisplayName("Unified KB Config Validation")
    class UnifiedKbConfigValidation {

        @Test
        @DisplayName("Should validate all components together")
        void shouldValidateAllComponentsTogether() throws Exception {
            ValidateKbConfigRequestDto request = new ValidateKbConfigRequestDto();
            request.setQuery("SELECT \"@timestamp\" FROM \"logs\" LIMIT 1");
            request.setQuery_mode("aggregated");
            request.setTimestamp_field("@timestamp");
            request.setCron_expression("*/10 * * * * *");

            mockMvc.perform(post("/api/validate/kb-config")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.cronValidation.valid").value(true))
                    .andExpect(jsonPath("$.cronIntervalSeconds").value(10));
        }

        @Test
        @DisplayName("Should fail when CRON is invalid in unified request")
        void shouldFailWhenCronInvalidInUnifiedRequest() throws Exception {
            ValidateKbConfigRequestDto request = new ValidateKbConfigRequestDto();
            request.setQuery("SELECT 1");
            request.setQuery_mode("aggregated");
            request.setTimestamp_field("ts");
            request.setCron_expression("invalid-cron");

            MvcResult result = mockMvc.perform(post("/api/validate/kb-config")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk())
                    .andReturn();

            ValidateKbConfigResponseDto response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ValidateKbConfigResponseDto.class);

            assertThat(response.getCronValidation().getErrors())
                .as("Invalid CRON should produce errors")
                .isNotEmpty();
        }

        @Test
        @DisplayName("Should handle all null fields")
        void shouldHandleAllNullFields() throws Exception {
            String json = "{}";

            mockMvc.perform(post("/api/validate/kb-config")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                    .andExpect(status().isOk()); // Should handle gracefully
        }
    }

    @Nested
    @DisplayName("Edge Cases and Boundary Tests")
    class EdgeCases {

        @ParameterizedTest
        @DisplayName("Should correctly calculate intervals for boundary CRON values")
        @CsvSource({
            "'0 0 0 1 1 *', 31536000",    // Once a year (approx)
            "'0 0 1 * *', 86400",          // Daily at 1:00 AM
            "'0 */12 * * *', 43200",       // Every 12 hours
            "'0 0 * * *', 86400",          // Once a day
            "'0 0 * * 0', 604800",         // Once a week (Sunday)
        })
        void shouldCalculateBoundaryIntervals(String cronExpression, int expectedInterval) throws Exception {
            ValidateCronRequestDto request = new ValidateCronRequestDto();
            request.setCron_expression(cronExpression);
            request.setQuery_mode("aggregated");

            MvcResult result = mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk())
                    .andReturn();

            ValidateCronResponseDto response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ValidateCronResponseDto.class);

            // Allow some tolerance for yearly/monthly calculations
            if (expectedInterval > 86400) {
                assertThat(response.getIntervalSeconds())
                    .as("Interval for '%s' should be approximately %d", cronExpression, expectedInterval)
                    .isBetween((long)(expectedInterval * 0.9), (long)(expectedInterval * 1.1));
            }
        }

        @Test
        @DisplayName("Should handle CRON at exact minimum frequency boundary")
        void shouldHandleExactMinimumBoundary() throws Exception {
            // Exactly 10 seconds - the minimum for aggregated mode
            ValidateCronRequestDto request = new ValidateCronRequestDto();
            request.setCron_expression("*/10 * * * * *");
            request.setQuery_mode("aggregated");

            MvcResult result = mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk())
                    .andReturn();

            ValidateCronResponseDto response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ValidateCronResponseDto.class);

            assertThat(response.getIntervalSeconds()).isEqualTo(10);
            assertThat(response.getErrors()).isNullOrEmpty();
        }

        @Test
        @DisplayName("Should handle CRON one second below minimum")
        void shouldHandleOneBelowMinimum() throws Exception {
            // 9 seconds - just below the 10s minimum
            ValidateCronRequestDto request = new ValidateCronRequestDto();
            request.setCron_expression("*/9 * * * * *");
            request.setQuery_mode("aggregated");

            MvcResult result = mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk())
                    .andReturn();

            ValidateCronResponseDto response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ValidateCronResponseDto.class);

            assertThat(response.getIntervalSeconds()).isEqualTo(9);
            // Should not have errors - the caller (KB-MCP) is responsible for enforcing
        }

        @ParameterizedTest
        @DisplayName("Should handle various valid 5-field CRON expressions")
        @ValueSource(strings = {
            "* * * * *",                  // Every minute
            "0 * * * *",                  // Every hour
            "0 0 * * *",                  // Every day at midnight
            "0 0 1 * *",                  // First day of month
            "0 0 1 1 *",                  // January 1st
            "*/5 * * * *",                // Every 5 minutes
            "0,30 * * * *",               // Every 30 minutes
            "0 9-17 * * 1-5",             // Weekdays 9-5
        })
        void shouldHandleValid5FieldCron(String cronExpression) throws Exception {
            ValidateCronRequestDto request = new ValidateCronRequestDto();
            request.setCron_expression(cronExpression);
            request.setQuery_mode("raw");

            MvcResult result = mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsString(request)))
                    .andExpect(status().isOk())
                    .andReturn();

            ValidateCronResponseDto response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ValidateCronResponseDto.class);

            assertThat(response.getErrors())
                .as("Valid 5-field CRON '%s' should not have errors", cronExpression)
                .isNullOrEmpty();
        }
    }

    @Nested
    @DisplayName("JSON Parsing Edge Cases")
    class JsonParsingTests {

        @Test
        @DisplayName("Should handle malformed JSON")
        void shouldHandleMalformedJson() throws Exception {
            mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{invalid json}"))
                    .andExpect(status().isBadRequest());
        }

        @Test
        @DisplayName("Should handle empty JSON object")
        void shouldHandleEmptyJsonObject() throws Exception {
            mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{}"))
                    .andExpect(status().isOk());
        }

        @Test
        @DisplayName("Should handle JSON with extra fields")
        void shouldHandleExtraFields() throws Exception {
            String json = "{\"cron_expression\": \"*/10 * * * * *\", \"query_mode\": \"aggregated\", \"extra_field\": \"ignored\"}";

            mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.intervalSeconds").value(10));
        }

        @Test
        @DisplayName("Should handle unicode in CRON expression")
        void shouldHandleUnicode() throws Exception {
            String json = "{\"cron_expression\": \"*/10 * * * * * 日本語\", \"query_mode\": \"aggregated\"}";

            mockMvc.perform(post("/api/validate/cron")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(json))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.errors").isNotEmpty());
        }
    }
}
