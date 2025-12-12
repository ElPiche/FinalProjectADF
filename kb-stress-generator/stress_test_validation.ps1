Write-Host "This script has been moved to 'MCP/KB-MCP/scripts/stress_test_validation.ps1'"
Write-Host "Please run the script from the KB-MCP scripts folder instead of the repository root."
Write-Host "Examples:"
Write-Host "  pwsh MCP/KB-MCP/scripts/stress_test_validation.ps1" -ForegroundColor Cyan
Write-Host "  # Or run it interactively inside the KB-MCP Docker container as documented in 'MCP/KB-MCP/README.md'." -ForegroundColor DarkGray
exit 0
    
    try {
        $response = Invoke-WebRequest -Uri "$baseUrl/cron" -Method POST -ContentType "application/json" -Body $body -ErrorAction Stop
        $jsonResponse = $response.Content | ConvertFrom-Json
        
        $hasErrors = $null -ne $jsonResponse.errors -and $jsonResponse.errors.Count -gt 0
        $interval = $jsonResponse.intervalSeconds
        
        $testPassed = $false
        switch ($ExpectedResult) {
            "valid" { 
                $testPassed = -not $hasErrors -and $response.StatusCode -eq 200
                if ($ExpectedInterval -gt 0) {
                    $testPassed = $testPassed -and $interval -eq $ExpectedInterval
                }
            }
            "rejected" { 
                $testPassed = $hasErrors
            }
        }
        
        if ($testPassed) {
            Write-Host "[PASS] $TestName" -ForegroundColor Green
            if ($ExpectedResult -eq "valid") {
                Write-Host "       Interval: $interval seconds" -ForegroundColor DarkGray
            }
            $script:passed++
        } else {
            Write-Host "[FAIL] $TestName" -ForegroundColor Red
            Write-Host "       Expected: $ExpectedResult, Status: $($response.StatusCode), HasErrors: $hasErrors, Interval: $interval" -ForegroundColor DarkGray
            $script:failed++
        }
    }
    catch {
        $statusCode = 0
        if ($_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        
        if ($ExpectedResult -eq "rejected" -and $statusCode -eq 400) {
            Write-Host "[PASS] $TestName - Rejected with HTTP 400" -ForegroundColor Green
            $script:passed++
        }
        elseif ($ExpectedResult -eq "rejected") {
            Write-Host "[PASS] $TestName - Rejected (exception)" -ForegroundColor Green
            $script:passed++
        }
        else {
            Write-Host "[FAIL] $TestName - Exception: $($_.Exception.Message)" -ForegroundColor Red
            $script:failed++
        }
    }
}

function Test-QueryModeValidation {
    param(
        [string]$TestName,
        [string]$QueryMode,
        [string]$ExpectedResult  # "valid", "rejected"
    )
    
    $body = @{ query_mode = $QueryMode } | ConvertTo-Json
    
    try {
        $response = Invoke-WebRequest -Uri "$baseUrl/query-mode" -Method POST -ContentType "application/json" -Body $body -ErrorAction Stop
        $jsonResponse = $response.Content | ConvertFrom-Json
        
        $isValid = $jsonResponse.valid -eq $true
        
        if ($ExpectedResult -eq "valid" -and $isValid) {
            Write-Host "[PASS] $TestName" -ForegroundColor Green
            $script:passed++
        }
        elseif ($ExpectedResult -eq "rejected" -and -not $isValid) {
            Write-Host "[PASS] $TestName - Rejected with errors" -ForegroundColor Green
            $script:passed++
        }
        else {
            Write-Host "[FAIL] $TestName - Expected: $ExpectedResult, Got valid=$isValid" -ForegroundColor Red
            $script:failed++
        }
    }
    catch {
        $statusCode = 0
        if ($_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        
        if ($ExpectedResult -eq "rejected" -and $statusCode -eq 400) {
            Write-Host "[PASS] $TestName - Rejected with HTTP 400" -ForegroundColor Green
            $script:passed++
        }
        else {
            Write-Host "[FAIL] $TestName - Exception: $($_.Exception.Message)" -ForegroundColor Red
            $script:failed++
        }
    }
}

function Test-TimestampFieldValidation {
    param(
        [string]$TestName,
        [string]$TimestampField,
        [string]$ExpectedResult  # "valid", "rejected"
    )
    
    $body = @{ timestamp_field = $TimestampField } | ConvertTo-Json
    
    try {
        $response = Invoke-WebRequest -Uri "$baseUrl/timestamp-field" -Method POST -ContentType "application/json" -Body $body -ErrorAction Stop
        $jsonResponse = $response.Content | ConvertFrom-Json
        
        $isValid = $jsonResponse.valid -eq $true
        
        if ($ExpectedResult -eq "valid" -and $isValid) {
            Write-Host "[PASS] $TestName" -ForegroundColor Green
            $script:passed++
        }
        elseif ($ExpectedResult -eq "rejected" -and -not $isValid) {
            Write-Host "[PASS] $TestName - Rejected with errors" -ForegroundColor Green
            $script:passed++
        }
        else {
            Write-Host "[FAIL] $TestName - Expected: $ExpectedResult, Got valid=$isValid" -ForegroundColor Red
            $script:failed++
        }
    }
    catch {
        $statusCode = 0
        if ($_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        
        if ($ExpectedResult -eq "rejected" -and $statusCode -eq 400) {
            Write-Host "[PASS] $TestName - Rejected with HTTP 400" -ForegroundColor Green
            $script:passed++
        }
        else {
            Write-Host "[FAIL] $TestName - Exception: $($_.Exception.Message)" -ForegroundColor Red
            $script:failed++
        }
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "VALIDATION ENDPOINTS STRESS TEST" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# ============================================================================
# SECTION A: QUERY MODE VALIDATION (/api/validate/query-mode)
# ============================================================================

Write-Host "--- Section A1: Valid Query Modes ---" -ForegroundColor Yellow
Test-QueryModeValidation -TestName "query_mode: raw" -QueryMode "raw" -ExpectedResult "valid"
Test-QueryModeValidation -TestName "query_mode: aggregated" -QueryMode "aggregated" -ExpectedResult "valid"
Test-QueryModeValidation -TestName "query_mode: RAW (uppercase)" -QueryMode "RAW" -ExpectedResult "valid"
Test-QueryModeValidation -TestName "query_mode: AGGREGATED (uppercase)" -QueryMode "AGGREGATED" -ExpectedResult "valid"
Test-QueryModeValidation -TestName "query_mode: Raw (mixed)" -QueryMode "Raw" -ExpectedResult "valid"

Write-Host "`n--- Section A2: Invalid Query Modes (should be rejected) ---" -ForegroundColor Yellow
Test-QueryModeValidation -TestName "query_mode: empty" -QueryMode "" -ExpectedResult "rejected"
Test-QueryModeValidation -TestName "query_mode: whitespace" -QueryMode "   " -ExpectedResult "rejected"
Test-QueryModeValidation -TestName "query_mode: invalid" -QueryMode "invalid" -ExpectedResult "rejected"
Test-QueryModeValidation -TestName "query_mode: batch" -QueryMode "batch" -ExpectedResult "rejected"
Test-QueryModeValidation -TestName "query_mode: stream" -QueryMode "stream" -ExpectedResult "rejected"
Test-QueryModeValidation -TestName "query_mode: sql-injection" -QueryMode "'; DROP TABLE users;--" -ExpectedResult "rejected"

# ============================================================================
# SECTION B: TIMESTAMP FIELD VALIDATION (/api/validate/timestamp-field)
# ============================================================================

Write-Host "`n--- Section B1: Valid Timestamp Fields ---" -ForegroundColor Yellow
Test-TimestampFieldValidation -TestName "timestamp_field: @timestamp" -TimestampField "@timestamp" -ExpectedResult "valid"
Test-TimestampFieldValidation -TestName "timestamp_field: es_timestamp" -TimestampField "es_timestamp" -ExpectedResult "valid"
Test-TimestampFieldValidation -TestName "timestamp_field: timestamp" -TimestampField "timestamp" -ExpectedResult "valid"
Test-TimestampFieldValidation -TestName "timestamp_field: created_at" -TimestampField "created_at" -ExpectedResult "valid"
Test-TimestampFieldValidation -TestName "timestamp_field: event_time" -TimestampField "event_time" -ExpectedResult "valid"

Write-Host "`n--- Section B2: Invalid Timestamp Fields (should be rejected) ---" -ForegroundColor Yellow
Test-TimestampFieldValidation -TestName "timestamp_field: empty" -TimestampField "" -ExpectedResult "rejected"
Test-TimestampFieldValidation -TestName "timestamp_field: whitespace" -TimestampField "   " -ExpectedResult "rejected"
Test-TimestampFieldValidation -TestName "timestamp_field: with spaces" -TimestampField "time stamp" -ExpectedResult "rejected"
Test-TimestampFieldValidation -TestName "timestamp_field: leading space" -TimestampField " timestamp" -ExpectedResult "rejected"
Test-TimestampFieldValidation -TestName "timestamp_field: trailing space" -TimestampField "timestamp " -ExpectedResult "rejected"

# ============================================================================
# SECTION C: CRON VALIDATION (/api/validate/cron)
# ============================================================================

Write-Host "`n--- Section C1: Malformed CRON Expressions (should be rejected) ---" -ForegroundColor Yellow
Test-CronValidation -TestName "Empty string" -CronExpression "" -ExpectedResult "rejected"
Test-CronValidation -TestName "Whitespace only" -CronExpression "   " -ExpectedResult "rejected"
Test-CronValidation -TestName "Single asterisk" -CronExpression "*" -ExpectedResult "rejected"
Test-CronValidation -TestName "Two fields" -CronExpression "* *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Three fields" -CronExpression "* * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Four fields" -CronExpression "* * * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Seven fields" -CronExpression "* * * * * * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Eight fields" -CronExpression "* * * * * * * *" -ExpectedResult "rejected"

Write-Host "`n--- Section C2: Invalid Field Values (should be rejected) ---" -ForegroundColor Yellow
Test-CronValidation -TestName "Minute > 59" -CronExpression "60 * * * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Hour > 23" -CronExpression "* 24 * * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Day > 31" -CronExpression "* * 32 * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Month > 12" -CronExpression "* * * 13 *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Day of week > 7" -CronExpression "* * * * 8" -ExpectedResult "rejected"
Test-CronValidation -TestName "Negative minute" -CronExpression "-1 * * * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Day = 0" -CronExpression "* * 0 * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Month = 0" -CronExpression "* * * 0 *" -ExpectedResult "rejected"

Write-Host "`n--- Section C3: Invalid Syntax (should be rejected) ---" -ForegroundColor Yellow
Test-CronValidation -TestName "Letters in minute" -CronExpression "abc * * * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Letters in hour" -CronExpression "* def * * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Division by zero" -CronExpression "*/0 * * * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Range exceeds max" -CronExpression "1-70 * * * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "List with invalid" -CronExpression "1,2,60 * * * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Invalid range syntax" -CronExpression "1-2-3 * * * *" -ExpectedResult "rejected"
Test-CronValidation -TestName "Decimal value" -CronExpression "1.5 * * * *" -ExpectedResult "rejected"

Write-Host "`n--- Section C4: Valid 5-field CRON (Raw Mode >= 60s) ---" -ForegroundColor Yellow
Test-CronValidation -TestName "Every minute" -CronExpression "* * * * *" -QueryMode "raw" -ExpectedResult "valid" -ExpectedInterval 60
Test-CronValidation -TestName "Every 5 min" -CronExpression "*/5 * * * *" -QueryMode "raw" -ExpectedResult "valid" -ExpectedInterval 300
Test-CronValidation -TestName "Every hour" -CronExpression "0 * * * *" -QueryMode "raw" -ExpectedResult "valid" -ExpectedInterval 3600
Test-CronValidation -TestName "Every day" -CronExpression "0 0 * * *" -QueryMode "raw" -ExpectedResult "valid" -ExpectedInterval 86400

Write-Host "`n--- Section C5: Valid 6-field CRON (Aggregated Mode >= 10s) ---" -ForegroundColor Yellow
Test-CronValidation -TestName "Every 10 seconds" -CronExpression "*/10 * * * * *" -QueryMode "aggregated" -ExpectedResult "valid" -ExpectedInterval 10
Test-CronValidation -TestName "Every 15 seconds" -CronExpression "*/15 * * * * *" -QueryMode "aggregated" -ExpectedResult "valid" -ExpectedInterval 15
Test-CronValidation -TestName "Every 30 seconds" -CronExpression "*/30 * * * * *" -QueryMode "aggregated" -ExpectedResult "valid" -ExpectedInterval 30
Test-CronValidation -TestName "Every minute (6-field)" -CronExpression "0 * * * * *" -QueryMode "aggregated" -ExpectedResult "valid" -ExpectedInterval 60

Write-Host "`n--- Section C6: Frequency Floor Violations (should be rejected for aggregated) ---" -ForegroundColor Yellow
Test-CronValidation -TestName "Every 1 second (< 10s min)" -CronExpression "*/1 * * * * *" -QueryMode "aggregated" -ExpectedResult "rejected"
Test-CronValidation -TestName "Every 5 seconds (< 10s min)" -CronExpression "*/5 * * * * *" -QueryMode "aggregated" -ExpectedResult "rejected"
Test-CronValidation -TestName "Every 9 seconds (< 10s min)" -CronExpression "*/9 * * * * *" -QueryMode "aggregated" -ExpectedResult "rejected"

Write-Host "`n--- Section C7: Frequency Floor Violations (should be rejected for raw) ---" -ForegroundColor Yellow
Test-CronValidation -TestName "Every 10 seconds for raw (< 60s min)" -CronExpression "*/10 * * * * *" -QueryMode "raw" -ExpectedResult "rejected"
Test-CronValidation -TestName "Every 30 seconds for raw (< 60s min)" -CronExpression "*/30 * * * * *" -QueryMode "raw" -ExpectedResult "rejected"

Write-Host "`n--- Section C8: Injection/Security Tests (should be rejected) ---" -ForegroundColor Yellow
Test-CronValidation -TestName "SQL injection" -CronExpression "; DROP TABLE users;" -ExpectedResult "rejected"
Test-CronValidation -TestName "Command injection" -CronExpression '$(rm -rf /)' -ExpectedResult "rejected"
Test-CronValidation -TestName "Path traversal" -CronExpression "../../../etc/passwd" -ExpectedResult "rejected"
Test-CronValidation -TestName "XSS attempt" -CronExpression "<script>alert(1)</script>" -ExpectedResult "rejected"
Test-CronValidation -TestName "Null string" -CronExpression "null" -ExpectedResult "rejected"

Write-Host "`n--- Section C9: Query Mode in CRON Validation ---" -ForegroundColor Yellow
Test-CronValidation -TestName "Valid mode: aggregated" -CronExpression "*/10 * * * * *" -QueryMode "aggregated" -ExpectedResult "valid" -ExpectedInterval 10
Test-CronValidation -TestName "Valid mode: raw" -CronExpression "* * * * *" -QueryMode "raw" -ExpectedResult "valid" -ExpectedInterval 60
Test-CronValidation -TestName "Case insensitive: AGGREGATED" -CronExpression "*/10 * * * * *" -QueryMode "AGGREGATED" -ExpectedResult "valid"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "RESULTS SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Endpoints Tested:" -ForegroundColor White
Write-Host "  - /api/validate/query-mode" -ForegroundColor DarkGray
Write-Host "  - /api/validate/timestamp-field" -ForegroundColor DarkGray
Write-Host "  - /api/validate/cron" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Passed: $passed" -ForegroundColor Green
Write-Host "Failed: $failed" -ForegroundColor Red
Write-Host "Total:  $($passed + $failed)" -ForegroundColor Cyan

$percentage = [math]::Round(($passed / ($passed + $failed)) * 100, 1)
Write-Host "Success Rate: $percentage%" -ForegroundColor $(if ($percentage -ge 90) { "Green" } elseif ($percentage -ge 70) { "Yellow" } else { "Red" })

if ($failed -gt 0) {
    Write-Host "`n[WARNING] Some tests failed!" -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "`n[SUCCESS] All validation stress tests passed!" -ForegroundColor Green
    exit 0
}
