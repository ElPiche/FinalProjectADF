# Feature Specification: Dynamic Context-Aware Anomaly Detection (Revised)

## 1. Executive Summary

This feature introduces **Time Contexts** to the Anomaly Detection Framework. Instead of treating all data points equally, the system will distinguish between different time periods (e.g., "Monday Morning" vs. "Sunday Night", "Business Hours" vs. "Holidays"). This is achieved through a **Bucket Context Layer** that maps timestamps to semantic keys (e.g., `business_hours_14`, `holiday_xmas`).

**Architectural Standards:**
*   **Python-Centric Logic:** The complex `BucketResolver` logic resides in the Python Dispatcher.
*   **Java Extractor Role:** Remains a lightweight runner for SQL execution and scheduling.
*   **Unified Query Mode:** Supports both **RAW** (event-level) and **AGGREGATED** (pre-grouped) data via a single configuration structure.
*   **Micro-Batch Detection:** Detection runs via scheduled micro-batches using Elasticsearch `_msearch` for scalability.

---

## 2. Architecture & Data Flow

### 2.1 Components
1.  **Java Extractor (The Clock & Runner):**
    *   Schedules Training and Detection jobs.
    *   Executes Elasticsearch SQL queries.
    *   Validates and normalizes timestamps.
    *   Writes raw/aggregated data to MongoDB `series` collection.
    *   Triggers Python Dispatcher via HTTP for detection batches.

2.  **Python Dispatcher (The Brain):**
    *   **BucketResolver:** Resolves timestamps to semantic keys.
    *   **ETL Engine:** Reads `series`, applies bucketing, aggregates into `staging_buckets`, and saves to `trained_models`.
    *   **Detection Engine:** Receives batch requests, queries Elasticsearch (via `_msearch`), resolves contexts, and detects anomalies.

3.  **MongoDB Collections:**
    *   `kb_configs`: Configuration documents.
    *   `bucket_profiles`: Reusable time-context definitions.
    *   `series`: Temporary buffer for extracted data (Raw or Aggregated).
    *   `staging_buckets`: Intermediate aggregation during training.
    *   `trained_models`: Final statistical baselines (Renamed from `series_result`).

---

## 3. Core Concepts

### 3.1 Bucket Contexts
A **Bucket** is a semantic label for a specific time period.
*   **Granularity:** Can be `hourly` (e.g., `monday_09`, `monday_10`) or `block` (e.g., `weekend`, `holiday`).
*   **Priority:** Exceptions (Holidays) > Schedule (Workdays) > Fallback.

### 3.2 Unified Query Mode
Users configure `query_mode` to optimize for data volume.
*   **RAW Mode:** For < 1M rows. Query returns individual events. High granularity.
*   **AGGREGATED Mode:** For > 1M rows. Query uses `GROUP BY` to return pre-aggregated metrics. High performance.
*   **Constraint:** Both modes must return a valid ISO8601 timestamp field.

---

## 4. Data Models

### 4.1 KB Configuration (`kb_configs`)
```json
{
  "_id": "ObjectId(...)",
  "name": "API Latency Monitor",
  "elasticsearch_sql_query": "SELECT @timestamp, avg_latency FROM logs ...",
  "query_mode": {
    "type": "aggregated", // "raw" | "aggregated"
    "timestamp_field": "@timestamp" // Required
  },
  "bucket_profile_id": "profile_business_hours_v1",
  "algorithm": { // Singular
    "name": "zscore",
    "parameters": [
      {"dimension": "avg_latency", "is_active": true}
    ]
  },
  "scheduling": {
    "training_config": { "type": "static", "from": "...", "to": "..." },
    "detection_config": { "frequency": "*/5 * * * *" }
  }
}
```

### 4.2 Bucket Profile (`bucket_profiles`)
```json
{
  "_id": "profile_business_hours_v1",
  "timezone": "America/New_York",
  "exceptions": [
    { "bucket_base_key": "holiday_xmas", "rule": { "month": 12, "day": 25 }, "granularity": "block" }
  ],
  "schedule": [
    { "bucket_base_key": "workday", "days": [1,2,3,4,5], "time_range": {"start": "09:00", "end": "17:00"}, "granularity": "hourly" }
  ],
  "fallback": { "bucket_base_key": "off_hours", "granularity": "hourly" }
}
```

### 4.3 Trained Model (`trained_models`)
```json
{
  "kb_id": "ObjectId(...)",
  "dimension": "avg_latency",
  "bucket_key": "workday_14",
  "model_data": { "mean": 250, "std": 45, "n": 1000 },
  "last_trained": "2025-11-24T..."
}
```

---

## 5. Implementation Details (Pseudocode)

### 5.1 Bucket Resolver Logic (Python)
**Libraries:** `zoneinfo` (Timezones), `datetime`.

```python
class BucketResolver:
    def resolve(self, utc_timestamp):
        local_dt = utc_timestamp.astimezone(self.timezone)
        
        # 1. Check Exceptions (Holidays) - Priority 1
        if local_dt.date() in self.exceptions_map:
            return self.format_key(self.exceptions_map[local_dt.date()], local_dt.hour)

        # 2. Check Schedule (Workdays/Weekends) - Priority 2
        for rule in self.schedule:
            if self.matches_rule(local_dt, rule):
                return self.format_key(rule, local_dt.hour)

        # 3. Check Overnight Shifts (Yesterday's shift extending to today)
        # Fix: Use '<' for end time check to avoid overlap
        yesterday = local_dt - timedelta(days=1)
        for rule in self.schedule:
            if rule.is_overnight and self.matches_rule(yesterday, rule):
                if self.is_within_overnight_tail(local_dt, rule):
                    return self.format_key(rule, local_dt.hour)

        # 4. Fallback
        return self.format_key(self.fallback, local_dt.hour)
```

### 5.2 ETL Pipeline: Training (Python Dispatcher)
**Triggered by:** Java Extractor (after dumping data to `series`).

**Note on Data Extraction:** The Java Extractor uses Elasticsearch's cursor-based pagination (fetch_size=1000) to handle large result sets automatically. There is no row limit - it will extract ALL data matching the query's time range.

```python
def run_training_etl(job_id, kb_config):
    # 1. Fetch Raw/Aggregated Data from Series
    # Java Extractor has already paginated through Elasticsearch cursor
    cursor = db.series.find({"job_id": job_id})
    
    # 2. Resolve & Stage (Bulk Write Optimization)
    staging_ops = []
    for record in cursor:
        bucket_key = resolver.resolve(record['timestamp'])
        # Accumulate values in staging_buckets
        staging_ops.append(
            UpdateOne(
                {"job_id": job_id, "bucket_key": bucket_key},
                {"$push": {"values": record['value']}},
                upsert=True
            )
        )
        if len(staging_ops) >= 1000:
            db.staging_buckets.bulk_write(staging_ops, ordered=False)
            staging_ops = []
    
    if staging_ops:
        db.staging_buckets.bulk_write(staging_ops, ordered=False)

    # 3. Train Models
    model_ops = []
    for bucket in db.staging_buckets.find({"job_id": job_id}):
        stats = calculate_stats(bucket['values']) # Mean, StdDev
        # Save to trained_models (One doc per dimension/bucket)
        model_ops.append(
            UpdateOne(
                {"kb_id": kb_config.id, "bucket_key": bucket['bucket_key']},
                {"$set": {"model_data": stats, "last_trained": datetime.now()}},
                upsert=True
            )
        )
    
    if model_ops:
        db.trained_models.bulk_write(model_ops, ordered=False)

    # 4. Cleanup
    db.staging_buckets.delete_many({"job_id": job_id})
```

### 5.3 Detection Pipeline: Micro-Batch (Java & Python)

**Java Extractor (Scheduler):**
```java
// Runs every 1s
void scheduleDetection() {
    // 1. Find KBs due for detection (Offset Logic: hash(id) % interval)
    List<KB> batch = findDueKBs();
    
    // 2. Send Batch to Python
    httpClient.post("http://dispatcher/detect_batch", batch);
}
```

**Python Dispatcher (Worker):**
**Libraries:** `asyncio`, `elasticsearch-async`.

```python
async def detect_batch(kbs):
    # 1. Resolve Contexts
    now = datetime.now(UTC)
    contexts = {kb.id: resolver.resolve(now) for kb in kbs}
    
    # 2. Build Multi-Search Request (_msearch)
    msearch_body = []
    for kb in kbs:
        query = build_query(kb, window=kb.detection_window)
        msearch_body.append(query)
        
    # 3. Execute Async Search
    responses = await es_client.msearch(body=msearch_body)
    
    # 4. Detect Anomalies
    for kb, response in zip(kbs, responses):
        bucket_key = contexts[kb.id]
        baseline = get_cached_model(kb.id, bucket_key) # LRU Cache
        
        anomalies = detect(response.hits, baseline)
        if anomalies:
            save_anomalies(anomalies)
```

---

## 6. Testing Strategy (Definition of Done)

**CRITICAL INSTRUCTION TO THE DEVELOPER:**
The feature is considered **INCOMPLETE** until the `BucketResolver` and Integration components pass **ALL** of the following test scenarios.

### 6.1 Docker-First Testing Mandate
1.  **No Host Execution:** All tests must be executed inside the Docker containers (`kb-mcp`, `dispatcher`, `extractor`).
2.  **Container Rebuilds:** Any change to Python modules (`kb-mcp`, `MotorDA`) or Java code (`extractor`) requires a container rebuild (`docker-compose build`) before running tests.
3.  **Environment Variables:** Tests must respect the container's environment variables (e.g., `MONGO_URI`, `ELASTICSEARCH_URL`).
4.  **Timezone Consistency:** Tests must explicitly set the timezone (e.g., `os.environ['TZ'] = 'America/New_York'`) or use timezone-aware objects to avoid UTC drift issues inside containers.

### 6.2 Category A: Granularity & Segmentation Variants
*Verifies the system can handle the different "Shapes" of buckets requested by users.*

#### Test A.1: The "Daily Bucket" Strategy
*   **Scenario:** User wants one bucket for each day of the week.
*   **Configuration:** 7 Rules. Example Rule: `key: "monday"`, `days: [1]`, `time: 00:00-23:59`, `granularity: "block"`.
*   **Input 1:** A Monday at 14:00. -> **Expected:** `monday`.
*   **Input 2:** A Monday at 23:59. -> **Expected:** `monday`.
*   **Input 3:** A Tuesday at 00:01. -> **Expected:** `tuesday`.

#### Test A.2: The "Global Hourly" Strategy
*   **Scenario:** User wants 24 buckets (00-23) regardless of the day of the week.
*   **Configuration:** 1 Rule. `key: "global"`, `days: [1-7]`, `time: 00:00-23:59`, `granularity: "hourly"`.
*   **Input 1:** Monday at 14:15. -> **Expected:** `global_14`.
*   **Input 2:** Sunday at 14:45. -> **Expected:** `global_14`.

#### Test A.3: The "Workday vs. Weekend" Hourly Split
*   **Scenario:** Differentiating 9 AM on a Monday from 9 AM on a Saturday.
*   **Configuration:**
    1.  Rule: `key: "workday"`, `days: [1-5]`, `granularity: "hourly"`.
    2.  Rule: `key: "weekend"`, `days: [6,7]`, `granularity: "hourly"`.
*   **Input 1:** Monday 09:00. -> **Expected:** `workday_09`.
*   **Input 2:** Saturday 09:00. -> **Expected:** `weekend_09`.

#### Test A.4: The "Active vs. Quiet" Intra-Day Split
*   **Scenario:** Hourly buckets for business hours, but a single "Quiet" bucket for night.
*   **Configuration:**
    1.  Rule: `key: "active"`, `time: 09:00-17:00`, `granularity: "hourly"`.
    2.  Rule: `key: "quiet"`, `time: 17:01-08:59`, `granularity: "block"`.
*   **Input 1:** 14:30. -> **Expected:** `active_14`.
*   **Input 2:** 02:30. -> **Expected:** `quiet`.

### 6.3 Category B: Priority & Overlaps (The Waterfall)
*Verifies the system correctly resolves ambiguity when a timestamp matches multiple rules.*

#### Test B.1: The "Lunch Break" Override (Specific vs. General)
*   **Scenario:** A specific "Low Traffic" window exists inside a "High Traffic" day.
*   **Configuration:**
    1.  **Index 0 (High Priority):** `key: "lunch"`, `time: 12:00-13:00`.
    2.  **Index 1 (Low Priority):** `key: "workday"`, `time: 09:00-17:00`.
*   **Input:** Tuesday @ `12:30`.
*   **Expected Output:** `lunch` (or `lunch_12`).
*   **Fail Condition:** Output is `workday`.

#### Test B.2: The "Holiday" Override
*   **Scenario:** Christmas falls on a Monday. Standard Monday logic must NOT apply.
*   **Configuration:**
    1.  **Exceptions List:** `key: "xmas"`, `date: 2025-12-25`.
    2.  **Schedule List:** `key: "monday_work"`, `days: [1]`.
*   **Input:** `2025-12-25T10:00:00` (Assume it matches Monday).
*   **Expected Output:** `xmas`.
*   **Why:** Verifies `exceptions` are checked *before* `schedule`.

### 6.4 Category C: Complex Shifts (Overnight & Seasonality)
*Verifies logic across day boundaries and year boundaries.*

#### Test C.1: The "Friday Night Party" (Yesterday Lookback)
*   **Scenario:** A shift starts Friday at 20:00 and ends Saturday at 04:00. We are detecting on Saturday morning.
*   **Configuration:** `days: [5]` (Friday), `start: "20:00"`, `end: "04:00"`, `key: "party_shift"`.
*   **Input:** Saturday Morning @ `02:00`.
*   **Expected Output:** `party_shift`.
*   **Fail Condition:** Output is `fallback` or `saturday_generic`.
*   **Why:** Verifies the logic checks if *Yesterday's* active shift is still valid for *Today's* early morning.
*   **Fix Note:** Ensure logic uses `<` (exclusive) for end time check to avoid overlap at exactly 04:00.

#### Test C.2: The "Winter" Wrap-Around
*   **Scenario:** A rule applies only in Winter (Dec, Jan, Feb).
*   **Configuration:** `key: "winter"`, `months: [12, 1, 2]`.
*   **Input 1:** `2025-12-31`. -> **Expected:** `winter`.
*   **Input 2:** `2026-01-01`. -> **Expected:** `winter`.
*   **Input 3:** `2026-03-01`. -> **Expected:** `fallback`.
*   **Fail Condition:** Jan 1st fails to match (Year wrap logic missing).

#### Test C.3: The "Empty Month" Safety
*   **Scenario:** User provides an empty list for months (Configuration Error).
*   **Configuration:** `key: "broken_rule"`, `months: []`.
*   **Input:** Any date.
*   **Expected Output:** Should NOT match `broken_rule`.

### 6.5 Category D: Technical Integrity & Sanitization
*Verifies the engine behaves robustly under code-level constraints.*

#### Test D.1: Naming Determinism (Sanitization)
*   **Scenario:** User inputs a messy bucket name.
*   **Configuration:** `bucket_base_key: "My Super Campaign! (2025)"`.
*   **Input:** Valid matching time.
*   **Expected Output:** `my_super_campaign_2025` (Snake case, no special chars).
*   **Fail Condition:** Output contains spaces, `!`, `()`, or uppercase letters.

#### Test D.2: Timezone Math (UTC vs Local)
*   **Scenario:** Database stores UTC. Profile is in `America/New_York` (EST).
*   **Configuration:** `timezone: "America/New_York"`, Rule: `start: "09:00"`.
*   **Input:** `14:00 UTC` (Which is `09:00 EST`).
*   **Expected Output:** Match.
*   **Fail Condition:** No match (System compared 14:00 UTC against 09:00 Rule directly).

#### Test D.3: Global Fallback (Null Profile)
*   **Scenario:** The user does not want to use buckets at all (`bucket_profile_id: null`).
*   **Expected Output:** All data points are tagged with a static hardcoded key (e.g., `global_default`).
*   **Fail Condition:** System crashes trying to invoke `resolver.resolve()` on a null object.

### 6.6 Category E: Advanced Robustness (Environment Edge Cases)
*Verifies the system handles Reality (DST, Clashing configs, Bad Inputs).*

#### Test E.1: The Phantom Hour (DST Spring Forward)
*   **Context:** In NY, 02:30 AM does not exist on March 9, 2025.
*   **Configuration:** `timezone: "America/New_York"`.
*   **Input:** A UTC timestamp that mathematically maps to NY 02:30.
*   **Requirement:** The Resolver **MUST NOT CRASH**. It should resolve to the adjacent hour or fallback.
*   **Fail Condition:** `ValueError` or Uncaught Exception.

#### Test E.2: The Exact Boundary (Inclusive vs Exclusive)
*   **Configuration:** Rule `start: "09:00"`, `end: "17:00"`.
*   **Input 1:** `17:00:59` (Minute 1020). -> **Expected:** Match.
*   **Input 2:** `17:01:00` (Minute 1021). -> **Expected:** No Match.
*   **Why:** Ensures buckets don't "bleed" data into the next minute.

#### Test E.3: Exception Collision (Priority Enforcement)
*   **Context:** Two Exceptions fall on the same date.
*   **Configuration:**
    1.  Index 0: `key: "black_friday"`, `date: 2025-11-28`.
    2.  Index 1: `key: "campaign_x"`, `date: 2025-11-28`.
*   **Input:** `2025-11-28`.
*   **Expected Output:** `black_friday`.
*   **Fail Condition:** Output is `campaign_x` (The last defined rule overwrote the first).
*   **Requirement:** The Implementation must explicitly check `if date not in lookup_map` before writing to ensure First Match Wins.

#### Test E.4: Invalid Configuration (Garbage Protection)
*   **Configuration:** `start: "99:99"`, `end: "25:00"`.
*   **Action:** Initialize `BucketResolver`.
*   **Expected Behavior:** The initialization should raise a clear `ValueError` OR log an error and safely skip the bad rule.
*   **Fail Condition:** Runtime crash during `resolve()` due to math errors.

### 6.7 Category F: Architecture & Integration (New Requirements)
*Verifies the new architectural components (Unified Query, Micro-Batch).*

#### Test F.1: Unified Query Mode Validation
*   **Scenario:** User configures `query_mode: "aggregated"` but forgets `GROUP BY`.
*   **Action:** Validate KB Config.
*   **Expected Output:** Validation Error: "Aggregated queries must include GROUP BY".
*   **Scenario:** User configures `query_mode` but `timestamp_field` is missing from SELECT.
*   **Expected Output:** Validation Error: "Query must SELECT timestamp_field".

#### Test F.2: Micro-Batch Detection Offset
*   **Scenario:** 100 KBs are scheduled for detection.
*   **Action:** Java Scheduler runs.
*   **Expected Behavior:** Not all 100 KBs trigger at the exact same second.
*   **Verification:** Check that `next_run_time` is distributed based on `hash(id) % interval`.

#### Test F.3: Staging Bucket Cleanup
*   **Scenario:** Training job completes successfully.
*   **Action:** Check `staging_buckets` collection.
*   **Expected Output:** No documents remaining for that `job_id`.
*   **Fail Condition:** Orphaned documents left in MongoDB.

---

## 7. Scalability & Performance Constraints

### 7.1 Minimum Frequency Enforcement
To prevent Denial-of-Service against the Elasticsearch cluster, the system must enforce hard limits on detection frequency based on the `query_mode`.
*   **RAW Mode:** Minimum frequency = **1 minute**.
*   **AGGREGATED Mode:** Minimum frequency = **10 seconds**.
*   **Validation:** The `KBConfig` validation logic must reject configurations violating these limits.

### 7.2 Deterministic Offsets (Thundering Herd Mitigation)
The Java Scheduler must not trigger all KBs simultaneously.
*   **Logic:** Calculate a deterministic offset for each KB: `offset = hash(kb_id) % interval_seconds`.
*   **Execution:** A KB scheduled for `*/5 * * * *` (every 300s) with `offset=12` runs at `T+12`, `T+312`, etc.

### 7.3 Efficient Batching (`_msearch`)
*   **Requirement:** The Python Dispatcher must use Elasticsearch's Multi-Search API (`_msearch`) to execute detection queries.
*   **Prohibited:** Do NOT use `UNION ALL` or sequential HTTP requests for batch detection.

### 7.4 AsyncIO & Caching
*   **Concurrency:** The Python Dispatcher must use `asyncio` for I/O operations. Multiprocessing is prohibited within the API context.
*   **Model Caching:** `trained_models` must be cached in memory (LRU Cache) for 5-10 minutes to avoid MongoDB lookups on every detection tick.

---

## 8. Migration Plan

1.  **Phase 1: Logic Core (Python):** Implement `BucketResolver`, Pydantic Models, and Test Suite.
2.  **Phase 2: Java/Python Bridge:** Update Java `KbMongo` entity, Extractor validation, and `series` normalization.
3.  **Phase 3: Training ETL:** Implement `staging_buckets` and Dual-Mode Training in Python.
4.  **Phase 4: Detection Switch:** Implement Java `DetectionSchedulerService` and Python `detect_batch` endpoint.
5.  **Phase 5: Validation:** Run Fire Test with new architecture.
