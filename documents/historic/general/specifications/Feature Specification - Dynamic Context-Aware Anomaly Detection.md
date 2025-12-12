# Feature Specification: Dynamic Context-Aware Anomaly Detection

## 1. Executive Summary & Architecture Scope

**The Objective**
Build an Anomaly Detection system capable of adapting to **Time Contexts** (e.g., distinguishing "Monday Morning" from "Sunday Night", or "Christmas Day" from a "Regular Tuesday"). Standard algorithms fail here because they treat all timestamps equally. We are introducing a **Bucket Context Layer** to solve this.

**The Architecture**
We are moving from a simple in-memory script to a robust **ETL Pipeline**:
1.  **Ingestion (Existing):** Java Extractor delivers raw time-series data to MongoDB.
2.  **Logic Engine (Python):** A `BucketResolver` class translates a Timestamp into a **Semantic Key** (e.g., `business_hours_14`, `holiday_lunar`) based on a reusable **Profile**.
3.  **Training (Batch/ETL):** A job runs (Static or Rolling), resolves keys for historical data, buffers them into a `staging_buckets` collection, calculates stats, and saves them to `trained_models`.
4.  **Detection (Real-Time):** A lightweight process resolves the *current* key and fetches the matching model to compare against live data.

---

Here is the corrected **Definition of Done** section with the indices fixed. **Category G** has been renamed to **Category E** to follow the logical sequence (A, B, C, D, E
# 2. Definition of Done (Quality Gates & Test Suite)

**CRITICAL INSTRUCTION TO THE DEVELOPER:**
The feature is considered **INCOMPLETE** until the `BucketResolver` passes **ALL** of the following test scenarios.

### 🚫 ZERO TOLERANCE FOR "TEST CHEATING"
1.  **No Mocking Logic:** You are strictly forbidden from implementing the resolution logic *inside* the test file to make tests pass.
2.  **Import the Real Class:** The tests **MUST** import the actual `BucketResolver` class from the application source code.
3.  **Black Box Testing:** Tests must treat the Resolver as a Black Box. You supply the JSON Config + Timestamp, and you assert the String Output.

### 📝 Mandatory File Header
You must include the following comment block at the very top of your test file (`test_bucket_resolver.py`):

```python
"""
CRITICAL INTEGRITY CHECK:
-------------------------
1. This test suite must import the ACTUAL BucketResolver implementation.
2. Do not mock the internal logic of the resolver.
3. If a test fails, fix the Implementation, NOT the test expectations.
4. All 5 Categories (A-E) must pass for the feature to be accepted.
"""
```

---

## Category A: Granularity & Segmentation Variants
*Verifies the system can handle the different "Shapes" of buckets requested by users.*

### Test A.1: The "Daily Bucket" Strategy
*   **Scenario:** User wants one bucket for each day of the week.
*   **Configuration:** 7 Rules. Example Rule: `key: "monday"`, `days: [1]`, `time: 00:00-23:59`, `granularity: "block"`.
*   **Input 1:** A Monday at 14:00. -> **Expected:** `monday`.
*   **Input 2:** A Monday at 23:59. -> **Expected:** `monday`.
*   **Input 3:** A Tuesday at 00:01. -> **Expected:** `tuesday`.

### Test A.2: The "Global Hourly" Strategy
*   **Scenario:** User wants 24 buckets (00-23) regardless of the day of the week.
*   **Configuration:** 1 Rule. `key: "global"`, `days: [1-7]`, `time: 00:00-23:59`, `granularity: "hourly"`.
*   **Input 1:** Monday at 14:15. -> **Expected:** `global_14`.
*   **Input 2:** Sunday at 14:45. -> **Expected:** `global_14`.

### Test A.3: The "Workday vs. Weekend" Hourly Split
*   **Scenario:** Differentiating 9 AM on a Monday from 9 AM on a Saturday.
*   **Configuration:**
    1.  Rule: `key: "workday"`, `days: [1-5]`, `granularity: "hourly"`.
    2.  Rule: `key: "weekend"`, `days: [6,7]`, `granularity: "hourly"`.
*   **Input 1:** Monday 09:00. -> **Expected:** `workday_09`.
*   **Input 2:** Saturday 09:00. -> **Expected:** `weekend_09`.

### Test A.4: The "Active vs. Quiet" Intra-Day Split
*   **Scenario:** Hourly buckets for business hours, but a single "Quiet" bucket for night.
*   **Configuration:**
    1.  Rule: `key: "active"`, `time: 09:00-17:00`, `granularity: "hourly"`.
    2.  Rule: `key: "quiet"`, `time: 17:01-08:59`, `granularity: "block"`.
*   **Input 1:** 14:30. -> **Expected:** `active_14`.
*   **Input 2:** 02:30. -> **Expected:** `quiet`.

---

## Category B: Priority & Overlaps (The Waterfall)
*Verifies the system correctly resolves ambiguity when a timestamp matches multiple rules.*

### Test B.1: The "Lunch Break" Override (Specific vs. General)
*   **Scenario:** A specific "Low Traffic" window exists inside a "High Traffic" day.
*   **Configuration:**
    1.  **Index 0 (High Priority):** `key: "lunch"`, `time: 12:00-13:00`.
    2.  **Index 1 (Low Priority):** `key: "workday"`, `time: 09:00-17:00`.
*   **Input:** Tuesday @ `12:30`.
*   **Expected Output:** `lunch` (or `lunch_12`).
*   **Fail Condition:** Output is `workday`.

### Test B.2: The "Holiday" Override
*   **Scenario:** Christmas falls on a Monday. Standard Monday logic must NOT apply.
*   **Configuration:**
    1.  **Exceptions List:** `key: "xmas"`, `date: 2025-12-25`.
    2.  **Schedule List:** `key: "monday_work"`, `days: [1]`.
*   **Input:** `2025-12-25T10:00:00` (Assume it matches Monday).
*   **Expected Output:** `xmas`.
*   **Why:** Verifies `exceptions` are checked *before* `schedule`.

---

## Category C: Complex Shifts (Overnight & Seasonality)
*Verifies logic across day boundaries and year boundaries.*

### Test C.1: The "Friday Night Party" (Yesterday Lookback)
*   **Scenario:** A shift starts Friday at 20:00 and ends Saturday at 04:00. We are detecting on Saturday morning.
*   **Configuration:** `days: [5]` (Friday), `start: "20:00"`, `end: "04:00"`, `key: "party_shift"`.
*   **Input:** Saturday Morning @ `02:00`.
*   **Expected Output:** `party_shift`.
*   **Fail Condition:** Output is `fallback` or `saturday_generic`.
*   **Why:** Verifies the logic checks if *Yesterday's* active shift is still valid for *Today's* early morning.

### Test C.2: The "Winter" Wrap-Around
*   **Scenario:** A rule applies only in Winter (Dec, Jan, Feb).
*   **Configuration:** `key: "winter"`, `months: [12, 1, 2]`.
*   **Input 1:** `2025-12-31`. -> **Expected:** `winter`.
*   **Input 2:** `2026-01-01`. -> **Expected:** `winter`.
*   **Input 3:** `2026-03-01`. -> **Expected:** `fallback`.
*   **Fail Condition:** Jan 1st fails to match (Year wrap logic missing).

### Test C.3: The "Empty Month" Safety
*   **Scenario:** User provides an empty list for months (Configuration Error).
*   **Configuration:** `key: "broken_rule"`, `months: []`.
*   **Input:** Any date.
*   **Expected Output:** Should NOT match `broken_rule`.

---

## Category D: Technical Integrity & Sanitization
*Verifies the engine behaves robustly under code-level constraints.*

### Test D.1: Naming Determinism (Sanitization)
*   **Scenario:** User inputs a messy bucket name.
*   **Configuration:** `bucket_base_key: "My Super Campaign! (2025)"`.
*   **Input:** Valid matching time.
*   **Expected Output:** `my_super_campaign_2025` (Snake case, no special chars).
*   **Fail Condition:** Output contains spaces, `!`, `()`, or uppercase letters.

### Test D.2: Timezone Math (UTC vs Local)
*   **Scenario:** Database stores UTC. Profile is in `America/New_York` (EST).
*   **Configuration:** `timezone: "America/New_York"`, Rule: `start: "09:00"`.
*   **Input:** `14:00 UTC` (Which is `09:00 EST`).
*   **Expected Output:** Match.
*   **Fail Condition:** No match (System compared 14:00 UTC against 09:00 Rule directly).

### Test D.3: Global Fallback (Null Profile)
*   **Scenario:** The user does not want to use buckets at all (`bucket_profile_id: null`).
*   **Expected Output:** All data points are tagged with a static hardcoded key (e.g., `global_default`).
*   **Fail Condition:** System crashes trying to invoke `resolver.resolve()` on a null object.

---

## Category E: Advanced Robustness (Environment Edge Cases)
*Verifies the system handles Reality (DST, Clashing configs, Bad Inputs).*

### Test E.1: The Phantom Hour (DST Spring Forward)
*   **Context:** In NY, 02:30 AM does not exist on March 9, 2025.
*   **Configuration:** `timezone: "America/New_York"`.
*   **Input:** A UTC timestamp that mathematically maps to NY 02:30.
*   **Requirement:** The Resolver **MUST NOT CRASH**. It should resolve to the adjacent hour or fallback.
*   **Fail Condition:** `ValueError` or Uncaught Exception.

### Test E.2: The Exact Boundary (Inclusive vs Exclusive)
*   **Configuration:** Rule `start: "09:00"`, `end: "17:00"`.
*   **Input 1:** `17:00:59` (Minute 1020). -> **Expected:** Match.
*   **Input 2:** `17:01:00` (Minute 1021). -> **Expected:** No Match.
*   **Why:** Ensures buckets don't "bleed" data into the next minute.

### Test E.3: Exception Collision (Priority Enforcement)
*   **Context:** Two Exceptions fall on the same date.
*   **Configuration:**
    1.  Index 0: `key: "black_friday"`, `date: 2025-11-28`.
    2.  Index 1: `key: "campaign_x"`, `date: 2025-11-28`.
*   **Input:** `2025-11-28`.
*   **Expected Output:** `black_friday`.
*   **Fail Condition:** Output is `campaign_x` (The last defined rule overwrote the first).
*   **Requirement:** The Implementation must explicitly check `if date not in lookup_map` before writing to ensure First Match Wins.

### Test E.4: Invalid Configuration (Garbage Protection)
*   **Configuration:** `start: "99:99"`, `end: "25:00"`.
*   **Action:** Initialize `BucketResolver`.
*   **Expected Behavior:** The initialization should raise a clear `ValueError` OR log an error and safely skip the bad rule.
*   **Fail Condition:** Runtime crash during `resolve()` due to math errors.

---

## 3. Data Models (MongoDB)

### A. The KB Configuration (The Driver)
*Defines What, When, and How to train.*

```json
{
  "_id": "kb_zscore_geo",
  "name": "Geographic Traffic Pattern Analysis",
  "bucket_profile_id": "profile_geo_logic_v1", // Link to Logic (can be null for Global mode)
  
  "scheduling": {
    "training_config": {
      "type": "rolling", // Options: "static" | "rolling"
      "is_active": true,
      
      // Used if type="static"
      "static_settings": {
        "from": "2025-11-01T00:00:00Z",
        "to": "2025-12-01T00:00:00Z"
      },
      
      // Used if type="rolling"
      "rolling_settings": {
        "window_size": "30d",      // "Train on last 30 days"
        "cron_expression": "0 0 * * 0"
      }
    },
    "detection_config": {
      "frequency": "*/1 * * * *",
      "detection_window": 300
    }
  }
}
```

### B. The Bucket Profile (The Logic)
*Reusable rules. Contains NO stats. Defines Context.*

```json
{
  "_id": "profile_geo_logic_v1", 
  "name": "Standard Business vs Off-Hours",
  "timezone": "America/New_York", 

  // PRIORITY 1: EXCEPTIONS (Holidays)
  "exceptions": [
    {
      "name": "Christmas",
      "bucket_base_key": "holiday_xmas",
      "calendar_system": "gregorian", 
      "granularity": "block", // "block" = All hours share one bucket
      "rule": { "month": 12, "day": 25 }
    }
  ],

  // PRIORITY 2: SCHEDULE (Waterfall Logic - Specific First!)
  "schedule": [
    {
      "bucket_base_key": "summer_fridays",
      "granularity": "hourly",
      "days": [5],            // Friday
      "months": [12, 1, 2],   // Dec, Jan, Feb (Seasonality)
      "time_range": { "start": "09:00", "end": "14:00" }
    },
    {
      "bucket_base_key": "business_hours", // General Rule
      "granularity": "hourly", // Generates 'business_hours_09', 'business_hours_10'...
      "days": [1, 2, 3, 4, 5],
      // "months": (omitted implies 1-12)
      "time_range": { "start": "09:00", "end": "17:00" }
    }
  ],

  // PRIORITY 3: FALLBACK
  "fallback": {
    "bucket_base_key": "off_hours",
    "granularity": "hourly"
  }
}
```

### C. The Staging Buckets (Intermediate)
*Temporary collection `staging_buckets`. Populated during Training ETL.*

```json
{
  "_id": "mongo_oid",
  "job_id": "uuid_run_12345",   // MANDATORY: Isolates parallel training jobs
  "kb_id": "kb_zscore_geo",
  "bucket_key": "business_hours_14", 
  "values": [200, 210, 195, 400, ...], 
  "created_at": "2025-11-25T10:00:00Z" // TTL Index target (24h)
}
```

### D. The Trained Models (Result)
*Permanent collection `trained_models`.*

```json
{
  "_id": "auto_generated_id",
  "kb_id": "kb_zscore_geo",     
  "bucket_key": "business_hours_14",     
  "last_trained": "2025-11-25T00:00:00Z",
  "model_data": { 
    "mean": 250.5, 
    "std_dev": 45.2,
    "sample_size": 500
  } 
}
```

---

## 4. The Core Engine: `BucketResolver` (Python)

**Instruction:** Implement this class exactly as described to handle the logic edge cases.

```python
import datetime
import re
from zoneinfo import ZoneInfo 
from typing import List, Dict, Any, Optional, Set

class BucketResolver:
    """
    Stateless engine. Input: Timestamp + Profile. Output: Deterministic Bucket Key.
    """

    def __init__(self, profile: Dict[str, Any], years_to_cache: List[int] = None):
        self.profile = profile
        try:
            self.timezone = ZoneInfo(profile.get("timezone", "UTC"))
        except Exception:
            self.timezone = datetime.timezone.utc
        
        # Optimization: Parse rules into integers & sets
        self.optimized_schedule = self._parse_schedule(profile.get("schedule", []))
        
        # Optimization: Pre-calculate holidays
        if years_to_cache is None:
            years_to_cache = [datetime.datetime.now().year]
        self.exception_lookup = self._precompute_exceptions(profile.get("exceptions", []), years_to_cache)
        
        self.fallback = profile.get("fallback", {"bucket_base_key": "unknown", "granularity": "hourly"})

    def _sanitize_key(self, key: str) -> str:
        """Enforces naming determinism (snake_case)"""
        key = key.lower().strip()
        key = re.sub(r'[^a-z0-9_]', '_', key)
        return re.sub(r'_+', '_', key)

    def _time_to_minutes(self, time_str: str) -> int:
        h, m = map(int, time_str.split(':'))
        return h * 60 + m

    def _parse_schedule(self, raw_schedule: List[Dict]) -> List[Dict]:
        optimized = []
        for rule in raw_schedule:
            start_min = self._time_to_minutes(rule['time_range']['start'])
            end_min = self._time_to_minutes(rule['time_range']['end'])
            
            clean_key = self._sanitize_key(rule['bucket_base_key'])
            
            # Month handling: Default to 1-12 if missing
            raw_months = rule.get('months', list(range(1, 13)))
            
            optimized.append({
                "bucket_base_key": clean_key,
                "granularity": rule['granularity'],
                "days_set": set(rule['days']),
                "months_set": set(raw_months), # Set Lookup for seasonality
                "start_min": start_min,
                "end_min": end_min,
                "is_overnight": start_min > end_min
            })
        return optimized

    def _precompute_exceptions(self, exceptions_config: List[Dict], years: List[int]) -> Dict[datetime.date, Dict]:
        """Calculates specific dates for Solar/Lunar holidays."""
        lookup_map = {}
        for year in years:
            for rule in exceptions_config:
                dates_found: Set[datetime.date] = set()
                
                # [TODO: Insert 'gregorian' / 'lunar_chinese' library logic here]
                # Populate dates_found
                
                clean_key = self._sanitize_key(rule['bucket_base_key'])
                for d in dates_found:
                    lookup_map[d] = {
                        "bucket_base_key": clean_key,
                        "granularity": rule['granularity']
                    }
        return lookup_map

    def resolve(self, utc_dt: datetime.datetime) -> str:
        """Determines Context Key using Waterfall Priority."""
        local_dt = utc_dt.astimezone(self.timezone)
        current_date = local_dt.date()
        current_month = local_dt.month
        current_iso_day = local_dt.isoweekday()
        current_hour = local_dt.hour
        current_mins = (current_hour * 60) + local_dt.minute

        # 1. Check Exceptions (Highest Priority)
        if current_date in self.exception_lookup:
            match = self.exception_lookup[current_date]
            if match['granularity'] == 'hourly':
                return f"{match['bucket_base_key']}_{current_hour:02d}"
            return match['bucket_base_key']

        # 2. Check Schedule (Today)
        for rule in self.optimized_schedule:
            if current_iso_day not in rule['days_set']: continue
            if current_month not in rule['months_set']: continue # Seasonality Check
            
            match = False
            if rule['is_overnight']:
                if current_mins >= rule['start_min'] or current_mins <= rule['end_min']: match = True
            else:
                if rule['start_min'] <= current_mins <= rule['end_min']: match = True

            if match:
                if rule['granularity'] == 'hourly':
                    return f"{rule['bucket_base_key']}_{current_hour:02d}"
                return rule['bucket_base_key']

        # 3. Check Yesterday's Overnight Shift (Crucial for 00:00-04:00 bugs)
        yesterday_date = current_date - datetime.timedelta(days=1)
        yesterday_iso = yesterday_date.isoweekday()
        yesterday_month = yesterday_date.month
        
        for rule in self.optimized_schedule:
            if yesterday_iso not in rule['days_set']: continue
            if not rule['is_overnight']: continue 
            if yesterday_month not in rule['months_set']: continue
            
            # If we are before the shift end time, we belong to yesterday's bucket
            if current_mins <= rule['end_min']:
                 if rule['granularity'] == 'hourly':
                    return f"{rule['bucket_base_key']}_{current_hour:02d}"
                 return rule['bucket_base_key']

        # 4. Fallback
        base = self._sanitize_key(self.fallback.get('bucket_base_key', 'unknown'))
        if self.fallback.get('granularity') == 'hourly':
             return f"{base}_{current_hour:02d}"
        return base
```

---

## 5. Implementation Workflow: The Training Job (ETL)

**Prerequisite:** `raw_data_collection` has data.
**Requirement:** Generate a unique `job_id` (UUID) at start.

### Stage 1: Resolve Dates
*Determine the query window based on Static vs Rolling.*

```python
def get_query_dates(training_config):
    if training_config['type'] == 'static':
        s = training_config['static_settings']
        return s['from'], s['to']
    elif training_config['type'] == 'rolling':
        # Parse "30d", "12h" etc
        # Return NOW() - window, NOW()
        pass
```

### Stage 2: Materialize (Extract & Transform)
*Iterate Raw Data $\to$ Resolve Key $\to$ Upsert to Staging.*

```python
def stage_training_data(kb_config, job_id, raw_collection, resolver, mongo_db):
    start_dt, end_dt = get_query_dates(kb_config['scheduling']['training_config'])
    
    query = { "timestamp": { "$gte": start_dt, "$lt": end_dt } }
    cursor = raw_collection.find(query)
    
    operations = []
    
    for record in cursor:
        key = resolver.resolve(record['timestamp'])
        
        # Batch Upsert via $push
        operations.append(
            UpdateOne(
                filter={ "job_id": job_id, "kb_id": kb_config['_id'], "bucket_key": key },
                update={ 
                    "$push": { "values": record['value'] },
                    "$setOnInsert": { "created_at": datetime.utcnow() }
                },
                upsert=True
            )
        )
        # Execute in batches of 1000...
```

### Stage 3: Train (Load)
*Iterate Staging $\to$ Compute Math $\to$ Save Model.*

```python
def train_from_staging(kb_config, job_id, mongo_db):
    # Query only this specific Job ID to avoid collision
    cursor = mongo_db.staging_buckets.find({"job_id": job_id})
    
    for bucket_doc in cursor:
        key = bucket_doc['bucket_key']
        values = bucket_doc['values']
        
        # --- ALGORITHM SPECIFIC MATH (Z-Score Example) ---
        mean = sum(values) / len(values)
        variance = sum([((x - mean) ** 2) for x in values]) / len(values)
        std_dev = variance ** 0.5
        # -------------------------------------------------

        # Save to 'trained_models'
        mongo_db.trained_models.update_one(
            filter={ "kb_id": kb_config['_id'], "bucket_key": key },
            update={
                "$set": {
                    "last_trained": datetime.utcnow(),
                    "model_data": { "mean": mean, "std_dev": std_dev, "n": len(values) }
                }
            },
            upsert=True
        )
```

### Stage 4: Cleanup
*Delete Staging Data for this `job_id`.*

---

## 6. Implementation Workflow: The Detection Job

**Prerequisite:** Real-time execution.

1.  **Resolve Context:**
    ```python
    now = datetime.datetime.now(datetime.timezone.utc)
    key = resolver.resolve(now) # e.g. "business_hours_14"
    ```
2.  **Fetch Model:**
    *   Query `trained_models` in Mongo.
    *   Filter: `{ kb_id: current_kb_id, bucket_key: key }`.
3.  **Execute Logic:**
    *   Load `model_data`.
    *   Compare incoming data against `model_data.mean / std_dev`.

---

## 7. Profile Builder Helper (Python)

*Use this to generate Profile JSONs programmatically.*

```python
class BucketProfileBuilder:
    def __init__(self, name, timezone="UTC"):
        self.profile = {
            "name": name, "timezone": timezone,
            "exceptions": [], "schedule": [],
            "fallback": {"bucket_base_key": "unknown", "granularity": "hourly"}
        }

    def add_schedule(self, key, days_list, start_str, end_str, months_list=None, granularity="hourly"):
        rule = {
            "bucket_base_key": key, "granularity": granularity,
            "days": days_list, 
            "time_range": {"start": start_str, "end": end_str}
        }
        if months_list:
            rule["months"] = months_list
        self.profile["schedule"].append(rule)
        return self

    # ... add methods for exceptions ...
    
    def build(self):
        return self.profile
```

---

## 8. Critical Technical Constraints

1.  **Concurrency:** Always use `job_id` in `staging_buckets` queries.
2.  **Indexing:**
    *   `staging_buckets`: `{ "job_id": 1, "kb_id": 1 }`
    *   `staging_buckets`: `{ "created_at": 1 }` (TTL: 24h)
3.  **Global Fallback:** If `bucket_profile_id` is null in the KB, bypass the Resolver and use a hardcoded key (e.g., `"global_default"`).

---

---

# TECHNICAL REVIEW & IMPLEMENTATION CRITIQUE

**Review Date:** November 24, 2025  
**Reviewer Role:** Architecture & Integration Reviewer  
**Review Scope:** Alignment with existing codebase, identification of pitfalls, migration path analysis

---

## EXECUTIVE SUMMARY

This specification represents a **significant architectural improvement** that addresses real limitations in the current bucketing approach. The proposed solution is **conceptually sound** and will dramatically improve anomaly detection accuracy for time-contextual patterns. However, **substantial migration work** is required across the entire stack (Python KB-MCP, Java Extractor, Python Dispatcher). This review identifies **12 critical integration issues** and **8 architectural mismatches** that must be resolved before implementation.

**Overall Assessment:** ✅ **APPROVED WITH MANDATORY CORRECTIONS**  
**Implementation Risk:** 🟡 **MEDIUM-HIGH** (Multi-language refactoring, data migration)  
**Estimated Rework Scope:** 40-60% of existing ETL/Detection pipeline

---

## SECTION 1: CRITICAL NOMENCLATURE & ID MISMATCHES

### ❌ Issue 1.1: KB ID Field Mismatch
**Specification States:**
```json
{
  "_id": "kb_zscore_geo",
  "bucket_profile_id": "profile_geo_logic_v1"
}
```

**Current Implementation Reality:**
- MongoDB auto-generates `_id` as ObjectId (e.g., `"68f3e1e1a856aa9308751164"`)
- Current field structure uses `id` (String) NOT `_id` in Java entities
- KB-MCP Pydantic models do NOT define `_id` field (relies on MongoDB auto-generation)

**Required Correction:**
```python
# models.py - NEW Bucket-Aware KB Model
class BucketAwareKBConfig(BaseModel):
    # Do NOT include _id - MongoDB handles this
    name: str
    description: str
    change_flag: int = 0
    elasticsearch_sql_query: str  # UNIFIED QUERY (not split train/detect)
    scheduling: BucketSchedulingConfig
    bucket_profile_id: Optional[str] = None  # Links to bucket_profiles collection
    algorithm: AlgorithmConfig  # SINGULAR (new spec = 1 algo per KB)
```

**Java Entity Adjustment:**
```java
@Document(collection = "kb_configs")
public class KbMongo {
    @Id
    private String id;  // MongoDB ObjectId as String
    private String bucketProfileId;  // NEW FIELD
    // ... existing fields
}
```

**Action Required:** Update ALL references to `kb_id` in spec to clarify whether it means:
1. The MongoDB document `_id` (ObjectId)
2. The `name` field (human-readable identifier)
3. A composite key (needs new field)

---

### ❌ Issue 1.2: Collection Naming Conflicts

**Specification Proposes:**
- `staging_buckets` (new temporary collection)
- `trained_models` (new permanent collection)
- `bucket_profiles` (new configuration collection)

**Current Implementation Has:**
- `series` - Raw extracted time-series data
- `series_result` - Trained model baselines (Z-score buckets)
- `training_config` - Training metadata/status
- `kb_configs` - Knowledge base configurations

**Conflict Analysis:**
| Spec Collection | Purpose | Current Equivalent | Migration Strategy |
|-----------------|---------|-------------------|-------------------|
| `staging_buckets` | Temporary ETL buffer | None (direct to `series`) | ✅ **NEW** (no conflict) |
| `trained_models` | Algorithm baselines | `series_result` | ⚠️ **RENAME or MERGE** |
| `bucket_profiles` | Bucket logic definitions | None | ✅ **NEW** (no conflict) |
| `raw_data_collection` | Source data | `series` | ⚠️ **SEMANTIC SHIFT** |

**Critical Problem:** The spec uses `raw_data_collection` to imply "source data from Elasticsearch", but the current `series` collection is the **OUTPUT** of the Java Extractor after querying Elasticsearch. This is a **logical mismatch**.

**Proposed Resolution:**
1. **Keep `series`** as the raw extraction collection (rename mentally to "extracted_series")
2. **Rename `series_result`** → `trained_models` (exact match with spec)
3. **Add `staging_buckets`** as new temporary collection
4. **Add `bucket_profiles`** as new configuration collection

---

### ❌ Issue 1.3: Algorithm Field Name Collision

**Specification:**
```json
{
  "algorithm": {  // SINGULAR
    "name": "zscore",
    "parameters": [...]
  }
}
```

**Current Implementation (DEPRECATED Template):**
```json
{
  "algorithms": [  // PLURAL, ARRAY
    {
      "alg_name": "zscore",
      "alg_parameters": [...]
    }
  ]
}
```

**New-Spec Template (Already Aligned!):**
```json
{
  "algorithm": {  // SINGULAR (matches spec!)
    "name": "kmeans",
    "parameters": [...]
  }
}
```

**✅ Good News:** The `New-spec-KBConfigTemplate.json` ALREADY uses singular `algorithm`, so this matches the bucket spec perfectly.

**Action Required:**
1. Update Pydantic models in `models.py` to remove `algorithms: List[AlgorithmConfigItem]`
2. Add `algorithm: AlgorithmConfig` (singular)
3. Update Java `KbMongo.java` to change `List<Algorithm> algorithms` → `Algorithm algorithm`
4. Update ALL Extractor/Dispatcher code that iterates `config.algorithms` → access `config.algorithm` directly

---

## SECTION 2: ARCHITECTURAL INTEGRATION ISSUES

### ⚠️ Issue 2.1: Query Unification vs. Current Split Queries

**Specification Proposes:**
```json
{
  "elasticsearch_sql_query": "SELECT ... WHERE @timestamp >= '$from' AND @timestamp < '$to'",
  "scheduling": {
    "training_config": {
      "from": "2025-11-01",
      "to": "2025-12-01"
    },
    "detection_config": {
      "frequency": "*/1 * * * *"
    }
  }
}
```

**Current Implementation:**
```json
{
  "scheduling": {
    "training_config": {
      "training_query": "SELECT ...",  // SEPARATE QUERY
      "from": "...", "to": "..."
    },
    "detection_config": {
      "detection_query": "SELECT ...",  // SEPARATE QUERY
      "from": "...", "frequency": "..."
    }
  }
}
```

**Critical Difference:**
- **Current:** Training and Detection can use **DIFFERENT QUERIES** (e.g., aggregation levels, GROUP BY logic)
- **Spec:** Uses **ONE UNIFIED QUERY** with `$from`/`$to` placeholders

**Impact Analysis:**
1. ✅ **Simplifies validation** (only need to check one query)
2. ✅ **Reduces duplication** (DRY principle)
3. ⚠️ **Removes flexibility** for detection-specific aggregations
4. ✅ **Clean architecture** - unified query approach from the start

**Recommendation:**
**ACCEPT** the unified query approach because:
- Bucketing logic makes train/detect query differences obsolete
- Detection should use the SAME metrics as training for consistency
- Active development phase allows clean architectural decisions

**Implementation Requirements:**
1. KB-MCP validation: Ensure `elasticsearch_sql_query` contains `$from` and `$to`
2. Extractor: Implement `SchedulerService` with single query for both phases
3. Remove dual-query logic from codebase

---

### ⚠️ Issue 2.2: Scheduling Type ("static" vs "rolling") Not Implemented

**Specification Introduces:**
```json
{
  "scheduling": {
    "training_config": {
      "type": "rolling",  // NEW FIELD!
      "rolling_settings": {
        "window_size": "30d",
        "cron_expression": "0 0 * * 0"
      }
    }
  }
}
```

**Current Implementation:**
Only supports **STATIC** training (fixed `from`/`to` dates). NO rolling window logic exists.

**Critical Gap:**
The spec's Section 5 includes a `get_query_dates()` function that branches on `training_config['type']`, but:
1. Java Extractor has no concept of "rolling" training
2. Dispatcher has no CRON scheduler for re-training
3. MongoDB change streams only trigger on config changes, not time-based re-training

**Proposed Solution:**
1. **Phase 1 (MVP):** Implement ONLY static training (defer rolling)
2. **Phase 2:** Add new `TrainingSchedulerService` in Java that:
   - Watches `training_config.type == "rolling"`
   - Schedules periodic re-training via `rolling_settings.cron_expression`
   - Calculates `from`/`to` dynamically using `window_size`

**Risk:** If rolling training is REQUIRED for the spec's time-context features (e.g., "always train on last 30 days"), then this is **BLOCKING**. Need clarification.

---

### ⚠️ Issue 2.3: ETL Pipeline Redesign Required

**Current ETL Flow (Simplified):**
```
Extractor (Java) 
  → Query Elasticsearch 
  → Save to `series` collection (one doc per data point)
  → Trigger Dispatcher (Python) via change stream
  → Dispatcher reads `series`, trains model, saves to `series_result`
  → Detection reads `series_result` for baseline
```

**Proposed ETL Flow (Spec):**
```
Extractor (Java)
  → Query Elasticsearch
  → For each data point:
      → Resolve bucket key via BucketResolver
      → Upsert to `staging_buckets` (accumulate values per bucket)
  → Trigger Training Job
  → Training Job:
      → Read `staging_buckets`
      → Calculate stats per bucket
      → Save to `trained_models`
      → Delete `staging_buckets` for this job_id
```

**Critical Issues:**

#### 2.3.1: BucketResolver Must Run INSIDE Java Extractor
The spec assumes Python will resolve buckets, but the Java Extractor is what extracts data. Options:
1. **Option A:** Port `BucketResolver` to Java (maintain logic in 2 languages ❌)
2. **Option B:** Call Python microservice from Java via HTTP (adds latency ⚠️)
3. **Option C:** Save raw to `series`, then Python reads + resolves + writes to `staging_buckets` (extra step ✅)

**Recommendation:** **Option C** - Preserve existing `series` collection as raw buffer, add new Python step that:
```python
# New ETL Step: Bucket Staging Service
for record in mongo.series.find({"job_id": current_job_id}):
    bucket_key = resolver.resolve(record['timestamp'])
    mongo.staging_buckets.update_one(
        {"job_id": job_id, "bucket_key": bucket_key},
        {"$push": {"values": record['value']}},
        upsert=True
    )
```

#### 2.3.2: Job ID Management Missing
Current system has NO concept of `job_id` for training runs. Need to add:
- Generate UUID for each training execution
- Pass `job_id` through entire pipeline
- Use for cleanup and concurrency isolation

---

### ❌ Issue 2.4: Detection Phase Completely Breaks Current Model

**Current Detection (via change stream):**
```python
# Dispatcher watches `series` collection for new inserts
# Immediately processes each data point
for change in series_collection.watch():
    new_doc = change['fullDocument']
    baseline = load_from_series_result(kb_id, dimension)
    anomaly = detect_anomaly(new_doc['value'], baseline)
    if anomaly:
        save_to_elasticsearch(anomaly)
```

**Proposed Detection (spec):**
```python
# Scheduled CRON job (e.g., every 5 minutes)
now = datetime.now(UTC)
bucket_key = resolver.resolve(now)
baseline = load_from_trained_models(kb_id, bucket_key)
recent_data = query_elasticsearch_for_last_N_seconds()
anomaly = detect_anomaly(recent_data, baseline)
```

**Fundamental Conflict:**
1. Current system is **EVENT-DRIVEN** (MongoDB change streams)
2. Proposed system is **SCHEDULED** (CRON-based polling)

**Impact:**
- Must disable change stream detection entirely
- Must implement new CRON-based detection scheduler (similar to `SchedulerService`)
- Detection window logic (`detection_window: 3600`) must query Elasticsearch DIRECTLY, not rely on `series` collection

**Recommendation:**
Create new `DetectionSchedulerService` in Java Extractor that:
1. Runs on `detection_config.frequency` CRON
2. Queries last `detection_window` seconds from Elasticsearch
3. Calls Python Dispatcher with resolved bucket_key
4. Dispatcher loads baseline from `trained_models[kb_id][bucket_key]`

---

## SECTION 3: DATA MODEL VALIDATION ISSUES

### ⚠️ Issue 3.1: Bucket Profile Timezone Validation

**Spec Recommendation:**
```python
try:
    self.timezone = ZoneInfo(profile.get("timezone", "UTC"))
except Exception:
    self.timezone = datetime.timezone.utc
```

**Problem:** Silent fallback to UTC on invalid timezone hides configuration errors.

**Better Approach:**
```python
from zoneinfo import ZoneInfo, available_timezones

def validate_timezone(tz_str: str) -> str:
    if tz_str not in available_timezones():
        raise ValueError(f"Invalid timezone: {tz_str}. Must be from IANA database.")
    return tz_str
```

Add Pydantic validator to BucketProfile model.

---

### ⚠️ Issue 3.2: Month List Validation Gap

**Test C.3 Requirement:**
> "User provides an empty list for months (Configuration Error). Expected: Should NOT match."

**Spec Code:**
```python
raw_months = rule.get('months', list(range(1, 13)))  # Defaults to all months
```

**Problem:** Empty list `[]` will be truthy, so it won't trigger the default. But the logic later does:
```python
if current_month not in rule['months_set']:  # months_set = set([])
    continue  # This will ALWAYS skip because empty set contains nothing
```

**Fix Needed:**
```python
raw_months = rule.get('months')
if raw_months is None or len(raw_months) == 0:
    raw_months = list(range(1, 13))  # Explicit empty check
```

---

### ❌ Issue 3.3: Overnight Shift Logic Has Off-By-One Bug

**Test C.1 ("Friday Night Party"):**
> Input: Saturday 02:00, Rule: Friday 20:00-04:00  
> Expected: `party_shift`

**Spec Code (Yesterday Check):**
```python
yesterday_date = current_date - datetime.timedelta(days=1)
yesterday_iso = yesterday_date.isoweekday()

for rule in self.optimized_schedule:
    if yesterday_iso not in rule['days_set']: continue
    if not rule['is_overnight']: continue
    
    if current_mins <= rule['end_min']:  # BUG: Should be '<' not '<='
         return rule['bucket_base_key']
```

**Problem:** At exactly `04:00:00` (minute 240), this matches BOTH:
1. Yesterday's shift (because `240 <= 240`)
2. Potentially today's shift

**Fix:**
```python
if current_mins < rule['end_min']:  # Exclusive upper bound
```

---

## SECTION 4: ALGORITHM-SPECIFIC INTEGRATION

### ⚠️ Issue 4.1: Z-Score Current Implementation Uses Different Bucketing

**Current Z-Score Logic:**
```python
df["train_window"] = (
    (df["timestamp"].dt.hour * 3600) +
    (df["timestamp"].dt.minute * 60) +
    df["timestamp"].dt.second
) // time_window

buckets = {"workday": {}, "non_workday": {}}
```

**Spec Proposal:**
```python
# Buckets are pre-resolved BEFORE training
# Bucket keys are semantic strings like "business_hours_14"
buckets = {
    "business_hours_14": {"mean": 250, "std": 45},
    "off_hours_02": {"mean": 50, "std": 10}
}
```

**Critical Mismatch:**
1. Current Z-Score groups by **numeric bucket numbers** (0-23)
2. Current Z-Score has **binary workday flag** (True/False)
3. Proposed system has **semantic string keys** ("monday_morning", "xmas")

**Migration Required:**
Rewrite `train_baseline()` function to:
```python
def train_baseline_bucketed(kb_id: str, dimension: str, staging_data: Dict[str, List[float]]):
    """
    staging_data = {
        "business_hours_14": [200, 210, 195, ...],
        "weekend_09": [50, 45, 52, ...]
    }
    """
    trained_models = {}
    for bucket_key, values in staging_data.items():
        mean = np.mean(values)
        std = np.std(values) if np.std(values) > 0 else 1e-6
        z_scores = np.abs((values - mean) / std)
        threshold = np.percentile(z_scores, 99.5)
        
        trained_models[bucket_key] = {
            "mean": mean, "std": std, "threshold": threshold
        }
    return trained_models
```

**Action:** Deprecate `add_workday_flag()` and time-window bucketing. Replace with BucketResolver.

---

### ✅ Issue 4.2: Multiple Dimensions Per Bucket - **RESOLVED**

**FINAL ARCHITECTURE DECISION (Post-Performance Analysis):**

```
1 KB = 1 Elasticsearch Query = 1 Algorithm + Multiple Dimensions

Key Principle: Dimensions from the SAME query MUST share a KB for performance.
```

**Rationale:**
Performance testing shows that separate KBs cause **10-100× increased Elasticsearch load** for large datasets:
- **Bad:** 10 dimensions = 10 KBs = 10 queries scanning 3B rows = 30B total scans
- **Good:** 10 dimensions = 1 KB = 1 query scanning 3B rows = 3B total scans

**KB Config Model (FINAL):**
```json
{
  "_id": "ObjectId(...)",
  "name": "HTTP Status Monitoring",
  "elasticsearch_sql_query": "SELECT @timestamp, status_200, status_404, status_500 FROM logs WHERE @timestamp >= '$from' AND @timestamp < '$to'",
  "bucket_profile_id": "profile_business_hours",
  "algorithm": {
    "name": "zscore",
    "parameters": [
      {"dimension": "status_200", "is_active": true},
      {"dimension": "status_404", "is_active": true},
      {"dimension": "status_500", "is_active": false}  // Can disable without new KB
    ]
  }
}
```

**trained_models Storage (Option A - Separate Documents):**
```json
// Document 1
{
  "_id": "ObjectId(...)",
  "kb_id": "ObjectId(kb123)",
  "dimension": "status_200",
  "bucket_key": "business_hours_14",
  "model_data": {"mean": 250, "std": 45}
}

// Document 2
{
  "_id": "ObjectId(...)",
  "kb_id": "ObjectId(kb123)",
  "dimension": "status_404",
  "bucket_key": "business_hours_14",
  "model_data": {"mean": 5, "std": 2}
}

// Index: { kb_id: 1, dimension: 1, bucket_key: 1 } UNIQUE
```

**Why Option A (Separate Documents)?**
- ✅ **Query efficiency:** `db.trained_models.findOne({kb_id, dimension, bucket_key})`
- ✅ **Atomic updates:** Update one dimension without locking others
- ✅ **Dimension-level metadata:** Each model tracks its own training stats
- ✅ **Scales horizontally:** MongoDB can shard by `{kb_id, dimension}`

**Flexibility Preserved:**
1. **Different bucket profiles?** → Create separate KBs (acceptable query duplication)
2. **Different detection frequencies?** → Create separate KBs
3. **Disable one dimension?** → Set `is_active: false` in parameters
4. **Different algorithms?** → Create separate KBs (e.g., zscore vs kmeans)

**When to use separate KBs:**
- Dimensions need different time contexts (e.g., hourly vs daily buckets)
- Dimensions have different alerting priorities (e.g., critical vs informational)
- Queries would return different data (e.g., logs vs metrics indices)

**When to use unified KB:**
- ✅ Dimensions from same Elasticsearch query
- ✅ Same time context requirements
- ✅ Data volume >100K rows (performance critical)
- ✅ Logical grouping (e.g., "all HTTP status codes")

---

## SECTION 5: TESTING FRAMEWORK ISSUES

### ⚠️ Issue 5.1: Test Suite Must Use Real MongoDB/Elasticsearch

**Spec Test Requirements:**
```python
"""
CRITICAL INTEGRITY CHECK:
1. This test suite must import the ACTUAL BucketResolver implementation.
2. Do not mock the internal logic of the resolver.
"""
```

**Problem:** Category D.2 (Timezone Math) and Category E.1 (DST) tests REQUIRE:
1. Real `pytz` or `zoneinfo` calculations
2. Actual timezone database (IANA)
3. Docker container might be in UTC, causing test failures

**Solution:**
```python
# test_bucket_resolver.py
import os
os.environ['TZ'] = 'America/New_York'  # Force timezone for tests

@pytest.fixture
def ny_profile():
    return {
        "timezone": "America/New_York",
        "schedule": [...]
    }
```

---

### ❌ Issue 5.2: Test E.3 (Exception Collision) Exposes Spec Bug

**Test E.3:**
> Two exceptions on same date, Index 0 should win.

**Spec Code (Section 4.8):**
```python
for rule in exceptions_config:
    for d in dates_found:
        lookup_map[d] = {  # OVERWRITES if d already exists!
            "bucket_base_key": clean_key,
            "granularity": rule['granularity']
        }
```

**Bug Confirmed:** Dict assignment WILL overwrite. Last exception wins, not first.

**Fix Required:**
```python
for d in dates_found:
    if d not in lookup_map:  # Only write if not already present
        lookup_map[d] = {...}
```

---

## SECTION 6: OPERATIONAL & DEPLOYMENT CONCERNS

### ⚠️ Issue 6.1: TTL Index on `staging_buckets` May Delete Active Jobs

**Spec Requirement:**
```json
{ "created_at": 1 }  // TTL: 24h
```

**Risk:** If training takes >24 hours (e.g., large dataset, slow query), MongoDB will DELETE the staging data mid-job.

**Better Approach:**
```python
# Add explicit cleanup instead of TTL
def cleanup_staging_buckets(job_id):
    mongo.staging_buckets.delete_many({"job_id": job_id})

# Call AFTER training completes successfully
```

Or use status field:
```json
{
  "job_id": "...",
  "status": "completed",  // "pending" | "completed" | "failed"
  "completed_at": "2025-11-24T..."
}
```
TTL index on `completed_at` with 24h expiry.

---

### ⚠️ Issue 6.2: No Error Handling for Partial Bucket Resolution

**Scenario:** BucketResolver crashes mid-ETL due to invalid profile.

**Current Impact:**
- `staging_buckets` has partial data
- `series` collection has unprocessed records
- No rollback mechanism

**Required:**
1. Wrap ETL in transaction (MongoDB 4.0+ replica set supports this)
2. Add `job_status` tracking:
   ```json
   {
     "job_id": "uuid",
     "status": "failed",
     "error": "Invalid timezone in profile",
     "timestamp": "..."
   }
   ```
3. Implement retry logic or admin alerts

---

## SECTION 7: MIGRATION STRATEGY RECOMMENDATIONS

### Phase 1: Foundation (Week 1-2)
1. ✅ Create `bucket_profiles` collection + validation
2. ✅ Implement `BucketResolver` class (Python only)
3. ✅ Add comprehensive unit tests (Categories A-E)
4. ✅ Create `BucketProfileBuilder` helper

### Phase 2: Data Model Migration (Week 2-3)
1. ⚠️ Update `New-spec-KBConfigTemplate.json` to add `bucket_profile_id`
2. ⚠️ Migrate Pydantic models in `models.py`
3. ⚠️ Update Java entities (`KbMongo.java`, `TrainConfig.java`)
4. ⚠️ Rename `series_result` → `trained_models`

### Phase 3: ETL Rewrite (Week 3-5)
1. ❌ Add `staging_buckets` collection
2. ❌ Implement Bucket Staging Service (Python)
3. ❌ Rewrite Z-Score training to use bucketed data
4. ❌ Update Dispatcher to load `trained_models` by bucket key

### Phase 4: Detection Refactor (Week 5-6)
1. ❌ Disable change stream detection
2. ❌ Implement `DetectionSchedulerService` (Java)
3. ❌ Update Dispatcher to resolve current bucket on detection
4. ❌ Integration testing with live Elasticsearch data

### Phase 5: Validation & Rollout (Week 6-7)
1. ⚠️ Run Fire Test with bucketed configuration
2. ⚠️ Validate accuracy against test datasets
3. ⚠️ Complete end-to-end integration testing
4. ✅ Deploy initial production system

---

---

## SECTION 10: UNIFIED QUERY MODE ARCHITECTURE (RAW vs AGGREGATED)

### 10.1 Design Philosophy: One Feature, Two Performance Profiles

**Core Principle:** The specification's bucketing system works identically whether data arrives as individual events (RAW) or pre-aggregated time series (AGGREGATED). Users choose the mode based on data volume, not feature requirements.

**Key Insight:** Query optimization is achieved through **SQL-level aggregation**, not code changes. The BucketResolver, trained_models, and detection logic remain unchanged.

---

### 10.2 Configuration Schema

```json
{
  "name": "web_traffic_monitor",
  "elasticsearch_sql_query": "...",  // Query syntax differs by mode
  
  "query_mode": {
    "type": "aggregated",           // "raw" | "aggregated"
    "timestamp_field": "time_bucket" // REQUIRED: Column name containing datetime for bucketing
  },
  
  "bucket_profile_id": "profile_business_hours_v1",  // Controls time bucketing granularity
  
  "scheduling": {
    "detection_config": {
      "frequency": "*/5 * * * *",
      "detection_window_seconds": 300  // How much recent data to query
    }
  },
  
  "algorithm": {
    "alg_name": "zscore",
    "alg_parameters": [
      {"dimension": "request_count"},  // Must match query output
      {"dimension": "error_rate"}
    ]
  }
}
```

**Critical Requirements:**
- `timestamp_field` is **MANDATORY** for all query modes (no defaults)
- Must reference a column that returns datetime/timestamp values
- Extractor validates the field exists and contains valid ISO8601 datetime
- Bucket profile's `granularity` setting controls time bucketing ("hourly" vs "block")

---

### 10.3 How Training Works in Both Modes

#### RAW Mode (< 1M rows)

**User Configuration:**
```json
{
  "query_mode": {
    "type": "raw",
    "timestamp_field": "@timestamp"  // Explicitly declares timestamp column
  }
}
```

**Step 1: Elasticsearch Query**
```sql
-- User writes standard SQL returning individual events
SELECT @timestamp, status_code, response_time
FROM "logs-*"
WHERE @timestamp >= '$from' AND @timestamp < '$to'
  AND region = 'us-east'
```
Result: 500K rows (one per log entry)

**Step 2: Extractor Validates and Saves to MongoDB**
```java
// Extractor normalizes timestamp field
String timestampField = config.getQueryMode().getTimestampField(); // "@timestamp"

for (Map<String, Object> row : queryResults) {
    // VALIDATION: Check field exists and is datetime type
    Object tsValue = row.get(timestampField);
    if (tsValue == null || !isValidDatetime(tsValue)) {
        throw new DataExtractionException("Invalid timestamp: " + timestampField);
    }
    
    // NORMALIZE: Always save as 'timestamp' field for Dispatcher
    Document doc = new Document()
        .append("timestamp", toISO8601(tsValue))  // Normalized field name
        .append("job_id", jobId)
        .append("kb_id", kbId)
        .append("status_code", row.get("status_code"))
        .append("response_time", row.get("response_time"))
        .append("phase", "training");
    
    seriesCollection.insertOne(doc);
}
```

```json
// series collection - one document per event (timestamp normalized)
{
  "job_id": "uuid-123",
  "kb_id": "web_traffic_monitor",
  "timestamp": "2025-11-15T14:23:45.678Z",  // Normalized from @timestamp
  "status_code": 200,
  "response_time": 145,
  "phase": "training"
}
```
Volume: 500K documents in `series`

**Step 3: Dispatcher Applies BucketResolver**
```python
# Reads all 500K documents
for doc in series_collection.find({"job_id": job_id}):
    # Resolve time context for EACH EVENT
    bucket_key = resolver.resolve(doc['timestamp'])
    # Group by context: business_hours_14, weekend_09, etc.
    staging_buckets[bucket_key].append(doc['response_time'])
```

**Step 4: Calculate Statistics Per Bucket**
```json
// trained_models collection
{
  "kb_id": "web_traffic_monitor",
  "dimension": "response_time",
  "bucket_key": "business_hours_14",  // Context: weekday 2-3pm
  "statistics": {
    "mean": 152.3,
    "std_dev": 23.5,
    "threshold_99_5": 198.7
  },
  "sample_count": 45000  // 45K events fell into this bucket
}
```

---

#### AGGREGATED Mode (> 10M rows)

**User Configuration:**
```json
{
  "query_mode": {
    "type": "aggregated",
    "timestamp_field": "time_bucket"  // User declares aggregated time column
  }
}
```

**Step 1: Elasticsearch Query with Pre-Aggregation**
```sql
-- User writes SQL with GROUP BY to reduce data volume
SELECT 
  DATE_TRUNC('minute', @timestamp) as time_bucket,
  COUNT(*) as request_count,
  AVG(response_time) as avg_response_time,
  SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) as error_count
FROM "logs-*"
WHERE @timestamp >= '$from' AND @timestamp < '$to'
  AND region = 'us-east'
GROUP BY time_bucket
ORDER BY time_bucket
```
Result: 43K rows (30 days × 24 hours × 60 minutes) instead of 3B

**Step 2: Extractor Validates and Normalizes Timestamp**
```java
// Extractor extracts 'time_bucket' column and renames to 'timestamp'
String timestampField = config.getQueryMode().getTimestampField(); // "time_bucket"

for (Map<String, Object> row : queryResults) {
    // VALIDATION: Ensure time_bucket exists and is datetime
    Object tsValue = row.get(timestampField);
    if (!isValidDatetime(tsValue)) {
        throw new DataExtractionException("time_bucket must be datetime");
    }
    
    // NORMALIZE: Rename time_bucket → timestamp
    Document doc = new Document()
        .append("timestamp", toISO8601(tsValue))  // Normalized
        .append("job_id", jobId)
        .append("kb_id", kbId)
        .append("request_count", row.get("request_count"))
        .append("avg_response_time", row.get("avg_response_time"))
        .append("error_count", row.get("error_count"))
        .append("phase", "training");
    
    seriesCollection.insertOne(doc);
}
```

```json
// series collection - one document per minute (timestamp normalized)
{
  "job_id": "uuid-123",
  "kb_id": "web_traffic_monitor",
  "timestamp": "2025-11-15T14:23:00Z",  // Normalized from time_bucket
  "request_count": 1847,                 // Pre-aggregated by Elasticsearch
  "avg_response_time": 156.4,
  "error_count": 3,
  "phase": "training"
}
```
Volume: 43K documents (100× reduction)

**Step 3: Dispatcher Applies BucketResolver (Unchanged)**
```python
# Reads 43K aggregated documents (not 3B individual events!)
for doc in series_collection.find({"job_id": job_id}):
    # Resolve time context - 'timestamp' field always exists (normalized by Extractor)
    bucket_key = resolver.resolve(doc['timestamp'])  # ✅ Always works
    # Group by context using pre-aggregated values
    staging_buckets[bucket_key].append(doc['request_count'])
```

**Step 4: Calculate Statistics on Aggregated Metrics**
```json
// trained_models collection
{
  "kb_id": "web_traffic_monitor",
  "dimension": "request_count",
  "bucket_key": "business_hours_14",
  "statistics": {
    "mean": 1823.5,      // Mean of per-minute counts
    "std_dev": 287.3,    // Std dev of per-minute counts
    "threshold_99_5": 2456.2
  },
  "sample_count": 750  // 750 minutes fell into this bucket context
}
```

**Critical Observations:** 
1. Both modes produce identical `trained_models` structure
2. Dispatcher always reads normalized `timestamp` field (doesn't care about original column name)
3. Extractor handles all timestamp validation and normalization
4. BucketResolver logic completely unchanged between modes

---

### 10.4 How Detection Works in Both Modes

#### RAW Mode Detection
```python
# Detection CRON triggers (e.g., every 5 minutes)
now = datetime.now(UTC)
bucket_key = resolver.resolve(now)  # "business_hours_14"

# Query recent raw events
query = f"""
  SELECT @timestamp, response_time
  FROM "logs-*"
  WHERE @timestamp >= '{now - detection_window}' 
    AND @timestamp < '{now}'
"""
recent_events = elasticsearch.query(query)  # Returns 5000 events

# Load context-specific baseline
baseline = trained_models.find_one({
    "kb_id": kb_id,
    "dimension": "response_time",
    "bucket_key": bucket_key
})

# Detect anomalies on individual events
for event in recent_events:
    zscore = (event['response_time'] - baseline['mean']) / baseline['std_dev']
    if abs(zscore) > baseline['threshold']:
        report_anomaly(event)
```

#### AGGREGATED Mode Detection
```python
# Detection CRON triggers
now = datetime.now(UTC)
bucket_key = resolver.resolve(now)  # "business_hours_14"

# Query recent aggregated data
query = f"""
  SELECT 
    DATE_TRUNC('minute', @timestamp) as time_bucket,
    COUNT(*) as request_count
  FROM "logs-*"
  WHERE @timestamp >= '{now - detection_window}'
    AND @timestamp < '{now}'
  GROUP BY time_bucket
"""
recent_buckets = elasticsearch.query(query)  # Returns 5 rows (one per minute)

# Load same baseline structure
baseline = trained_models.find_one({
    "kb_id": kb_id,
    "dimension": "request_count",
    "bucket_key": bucket_key
})

# Detect anomalies on aggregated metrics
for bucket in recent_buckets:
    zscore = (bucket['request_count'] - baseline['mean']) / baseline['std_dev']
    if abs(zscore) > baseline['threshold']:
        report_anomaly(bucket)
```

**Key Observation:** Detection logic is identical. Only the SQL query syntax differs.

---

### 10.5 Performance Comparison Table

| Metric | RAW Mode (3B rows, 30d) | AGGREGATED Mode (3B rows, 30d) |
|--------|-------------------------|----------------------------------|
| **Training Query Time** | 1800s (30 min) | 45s |
| **Rows Returned** | 3,000,000,000 | 43,200 (1-min buckets) |
| **Network Transfer** | ~300GB | ~4MB |
| **MongoDB Storage** | 600GB | 8MB |
| **Bucketing Time** | CRASHES (OOM) | 5s |
| **Total Training Time** | IMPOSSIBLE | 50s |
| **Detection Query Time** | 15s (5-min window) | 0.2s |
| **Real-time Viable** | ❌ No | ✅ Yes |

---

### 10.6 Feature Preservation Guarantee

**All Specification Features Work in Both Modes:**

1. **BucketResolver Context Logic**
   - RAW: `resolver.resolve(event_timestamp)`
   - AGGREGATED: `resolver.resolve(time_bucket)`
   - Both return same keys: "business_hours_14", "holiday_xmas", "weekend_09"

2. **Multi-Dimension Support**
   - RAW: `SELECT response_time, error_count, cpu_usage`
   - AGGREGATED: `SELECT AVG(response_time), SUM(errors), MAX(cpu)`
   - Both create separate `trained_models` per dimension

3. **Exception Handling (Holidays)**
   - RAW: Each event timestamp checked against exception dates
   - AGGREGATED: Each aggregated bucket timestamp checked
   - Same exception priority logic applies

4. **Overnight Shift Detection**
   - RAW: Individual events at 02:00 resolve to yesterday's shift
   - AGGREGATED: 02:00 time bucket resolves to yesterday's shift
   - Same "yesterday lookback" logic (Test C.1)

5. **Rolling Training Windows**
   - RAW: Query "last 30 days" returns all events
   - AGGREGATED: Query "last 30 days" with GROUP BY returns buckets
   - Both support periodic re-training

---

### 10.7 When to Use Each Mode

#### Use RAW Mode When:
- Data volume < 1M rows per training period
- Need exact event-level timestamps for investigation
- Detecting outliers on individual transactions (e.g., fraud detection)
- Elasticsearch query completes in < 10 seconds
- Total data fits in MongoDB (< 10GB)

#### Use AGGREGATED Mode When:
- Data volume > 10M rows per training period
- Elasticsearch query takes > 30 seconds in RAW mode
- Algorithm works on aggregate metrics (counts, rates, averages)
- 1-minute granularity sufficient for business context
- Real-time detection required (sub-second response)

**Decision Flowchart:**
```
Start
  ├─> Training data < 1M rows? ──YES──> RAW Mode
  │                            └─NO
  ├─> Can Elasticsearch aggregate? ──NO──> RAW Mode (with partitioning)
  │                               └─YES
  ├─> Is 1-minute granularity acceptable? ──NO──> RAW Mode
  │                                        └─YES
  └─> Use AGGREGATED Mode ✅
```

---

### 10.8 Implementation Strategy

**Phase 1: Strict Validation (No Defaults)**
```python
# models.py - Required configuration
class QueryModeConfig(BaseModel):
    type: Literal["raw", "aggregated"]
    timestamp_field: str  # REQUIRED - no default
    
    @model_validator(mode='after')
    def validate_timestamp_field(self):
        if not self.timestamp_field or self.timestamp_field.strip() == "":
            raise ValueError(
                "timestamp_field is REQUIRED. Specify the column name "
                "containing datetime values (e.g., '@timestamp', 'time_bucket')"
            )
        return self

class KBConfig(BaseModel):
    elasticsearch_sql_query: str
    query_mode: QueryModeConfig  # REQUIRED field
    bucket_profile_id: Optional[str] = None  # Can be null for global mode
    
    @model_validator(mode='after')
    def validate_timestamp_in_query(self):
        # Verify timestamp_field appears in SELECT clause
        if self.query_mode.timestamp_field not in self.elasticsearch_sql_query:
            raise ValueError(
                f"Query must SELECT '{self.query_mode.timestamp_field}'. "
                f"Current query: {self.elasticsearch_sql_query}"
            )
        return self
```

**Phase 2: Extractor Timestamp Normalization**
```python
# No code changes to BucketResolver, Dispatcher, or Algorithms!
# Extractor handles timestamp validation and normalization:

def execute_query(kb_config):
    query = kb_config.elasticsearch_sql_query
    results = elasticsearch_client.query(query)
    
    timestamp_field = kb_config.query_mode.timestamp_field
    
    for row in results:
        # VALIDATION 1: Field exists
        if timestamp_field not in row:
            raise DataExtractionException(
                f"Query missing timestamp field: {timestamp_field}. "
                f"Available columns: {list(row.keys())}"
            )
        
        # VALIDATION 2: Is datetime type
        ts_value = row[timestamp_field]
        if not is_valid_datetime(ts_value):
            raise DataExtractionException(
                f"Field '{timestamp_field}' must be datetime, got: {type(ts_value)}"
            )
        
        # NORMALIZE: Always save as 'timestamp' field
        doc = {
            "job_id": job_id,
            "kb_id": kb_config.id,
            "timestamp": to_iso8601(ts_value),  # Normalized name
            "phase": "training"
        }
        
        # Copy all other columns (dimensions)
        for key, value in row.items():
            if key != timestamp_field:  # Avoid duplication
                doc[key] = value
        
        series_collection.insert_one(doc)
```

**Phase 3: Enhanced Validation Logic**
```python
# KB-MCP validation.py
def validate_kb_config(kb_config):
    # VALIDATION 1: timestamp_field in query
    if kb_config.query_mode.timestamp_field not in kb_config.elasticsearch_sql_query:
        raise ValidationError(
            f"Query must SELECT '{kb_config.query_mode.timestamp_field}'"
        )
    
    # VALIDATION 2: Aggregated mode requires GROUP BY
    if kb_config.query_mode.type == "aggregated":
        if "GROUP BY" not in kb_config.elasticsearch_sql_query.upper():
            raise ValidationError("Aggregated queries must include GROUP BY")
    
    # VALIDATION 3: Dimension names in query
    for param in kb_config.algorithm.alg_parameters:
        if param.dimension not in kb_config.elasticsearch_sql_query:
            raise ValidationError(
                f"Dimension '{param.dimension}' not in SELECT clause"
            )
    
    # VALIDATION 4: Test query execution (optional but recommended)
    try:
        test_query = kb_config.elasticsearch_sql_query\
            .replace("$from", "'2025-01-01'")\
            .replace("$to", "'2025-01-02'") + " LIMIT 1"
        
        result = elasticsearch_client.query(test_query)
        if not result:
            return  # Empty result OK for validation
        
        # Verify timestamp_field exists in result
        if kb_config.query_mode.timestamp_field not in result[0]:
            raise ValidationError(
                f"Query returns {list(result[0].keys())}, "
                f"missing '{kb_config.query_mode.timestamp_field}'"
            )
        
        # Verify timestamp is datetime type
        ts_value = result[0][kb_config.query_mode.timestamp_field]
        if not is_datetime_type(ts_value):
            raise ValidationError(
                f"Field '{kb_config.query_mode.timestamp_field}' "
                f"must return datetime, got {type(ts_value)}"
            )
    except Exception as e:
        raise ValidationError(f"Query validation failed: {str(e)}")
```

---

### 10.9 Switching Between RAW and AGGREGATED Modes

**Scenario:** User wants to optimize an initially-configured RAW mode KB by switching to AGGREGATED for better performance.

**Step 1: Modify KB Configuration**
```json
// Original (RAW)
{
  "elasticsearch_sql_query": "SELECT @timestamp, status_code FROM logs WHERE...",
  "query_mode": {
    "type": "raw",
    "timestamp_field": "@timestamp"
  },
  "algorithm": {"alg_parameters": [{"dimension": "status_code"}]}
}

// Updated (AGGREGATED)
{
  "elasticsearch_sql_query": "SELECT DATE_TRUNC('minute', @timestamp) as time_bucket, COUNT(*) as status_code_count FROM logs WHERE... GROUP BY time_bucket",
  "query_mode": {
    "type": "aggregated",
    "timestamp_field": "time_bucket"  // Changed to match new column
  },
  "algorithm": {"alg_parameters": [{"dimension": "status_code_count"}]}  // Dimension name changes
}
```

**Step 2: Re-train Models**
- Set `training_config.is_active = true`
- Extractor triggers new training run with aggregated query
- New `trained_models` documents created with aggregated statistics
- Previous models are replaced

**Step 3: Detection Updates Automatically**
- Detection automatically uses new aggregated query
- No code changes needed

**Note:** All KBs MUST have explicit `query_mode` configuration. This is enforced by validation.

---

### 10.10 Architecture Diagram: Unified Query Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER CONFIGURATION                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ KB Config                                                 │   │
│  │ - query_mode: {type: "raw" | "aggregated"}              │   │
│  │ - elasticsearch_sql_query: "SELECT ..."                 │   │
│  │ - bucket_profile_id: "business_hours_v1"                │   │
│  │ - algorithm: {dimension: "metric_name"}                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     TRAINING PHASE                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
        ┌─────────────────────┴─────────────────────┐
        ↓ RAW Mode                    AGGREGATED Mode ↓
┌──────────────────────┐              ┌──────────────────────┐
│ Elasticsearch Query  │              │ Elasticsearch Query  │
│ SELECT @timestamp,   │              │ SELECT DATE_TRUNC    │
│   response_time      │              │   ('minute', @ts),   │
│ FROM logs            │              │   COUNT(*) AS count  │
│ WHERE ...            │              │ FROM logs            │
│                      │              │ WHERE ...            │
│ Returns: 3B rows     │              │ GROUP BY time_bucket │
│ Time: 30 minutes     │              │ Returns: 43K rows    │
│                      │              │ Time: 45 seconds     │
└──────────┬───────────┘              └──────────┬───────────┘
           │                                     │
           └────────────────┬────────────────────┘
                            ↓
                ┌───────────────────────┐
                │  MongoDB `series`     │
                │  - job_id             │
                │  - kb_id              │
                │  - timestamp          │
                │  - dimension values   │
                │  (Volume differs      │
                │   by mode)            │
                └───────────┬───────────┘
                            ↓
                ┌───────────────────────┐
                │  BucketResolver       │
                │  (UNCHANGED)          │
                │                       │
                │  For each timestamp:  │
                │  - Check exceptions   │
                │  - Check schedule     │
                │  - Check overnight    │
                │  - Return bucket_key  │
                └───────────┬───────────┘
                            ↓
                ┌───────────────────────┐
                │ staging_buckets       │
                │ Group by bucket_key:  │
                │ - business_hours_14   │
                │ - weekend_09          │
                │ - holiday_xmas        │
                └───────────┬───────────┘
                            ↓
                ┌───────────────────────┐
                │ Algorithm (UNCHANGED) │
                │ Calculate per bucket: │
                │ - mean, std_dev       │
                │ - percentiles         │
                │ - thresholds          │
                └───────────┬───────────┘
                            ↓
                ┌───────────────────────┐
                │  trained_models       │
                │  (SAME STRUCTURE)     │
                │  - kb_id              │
                │  - dimension          │
                │  - bucket_key         │
                │  - statistics         │
                └───────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     DETECTION PHASE                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
        ┌─────────────────────┴─────────────────────┐
        ↓ RAW Mode                    AGGREGATED Mode ↓
┌──────────────────────┐              ┌──────────────────────┐
│ Query last 5 min:    │              │ Query last 5 min:    │
│ SELECT response_time │              │ SELECT COUNT(*)      │
│ Returns: 5000 events │              │ GROUP BY minute      │
│ Time: 15 seconds     │              │ Returns: 5 rows      │
│                      │              │ Time: 0.2 seconds    │
└──────────┬───────────┘              └──────────┬───────────┘
           │                                     │
           └────────────────┬────────────────────┘
                            ↓
                ┌───────────────────────┐
                │  BucketResolver       │
                │  resolve(now)         │
                │  → "business_hours_14"│
                └───────────┬───────────┘
                            ↓
                ┌───────────────────────┐
                │  Load trained_models  │
                │  WHERE bucket_key =   │
                │    "business_hours_14"│
                └───────────┬───────────┘
                            ↓
                ┌───────────────────────┐
                │  Anomaly Detection    │
                │  (SAME ALGORITHM)     │
                │  Compare values vs    │
                │  bucket baseline      │
                └───────────┬───────────┘
                            ↓
                ┌───────────────────────┐
                │  Elasticsearch        │
                │  anomaly_results      │
                │  (anomalies only)     │
                └───────────────────────┘
```

**Key Observations:**
1. ✅ **BucketResolver logic unchanged** - Works on timestamps regardless of data source
2. ✅ **trained_models structure unchanged** - Same schema for both modes
3. ✅ **Algorithm code unchanged** - Processes grouped data identically
4. ✅ **Detection logic unchanged** - Selects baseline by bucket_key
5. ⚡ **Performance differs 100×** - Only at query execution layer
6. 🎯 **User controls optimization** - Via SQL query syntax, not code complexity

---

### 10.11 Real-World Example: Converting a KB

**Scenario:** User has "API Latency Monitor" tracking 50M requests/day across 10 endpoints.

**Original Configuration (RAW - Too Slow):**
```json
{
  "name": "api_latency_raw",
  "elasticsearch_sql_query": "SELECT @timestamp, endpoint, response_time FROM api_logs WHERE @timestamp >= '$from' AND @timestamp < '$to'",
  "query_mode": {
    "type": "raw",
    "timestamp_field": "@timestamp"
  },
  "bucket_profile_id": "business_hours_profile",
  "algorithm": {
    "alg_name": "zscore",
    "alg_parameters": [
      {"dimension": "response_time"}
    ]
  }
}
```
**Problem:** Training on 30 days = 1.5B rows, takes 45 minutes, MongoDB storage = 300GB

**Optimized Configuration (AGGREGATED - Fast):**
```json
{
  "name": "api_latency_aggregated",
  "elasticsearch_sql_query": "SELECT DATE_TRUNC('minute', @timestamp) as time_bucket, endpoint, AVG(response_time) as avg_response_time, PERCENTILE(response_time, 95) as p95_response_time FROM api_logs WHERE @timestamp >= '$from' AND @timestamp < '$to' GROUP BY time_bucket, endpoint",
  "query_mode": {
    "type": "aggregated",
    "timestamp_field": "time_bucket"  // Matches aggregated column
  },
  "bucket_profile_id": "business_hours_profile",  // SAME PROFILE!
  "algorithm": {
    "alg_name": "zscore",
    "alg_parameters": [
      {"dimension": "avg_response_time"},
      {"dimension": "p95_response_time"}
    ]
  }
}
```
**Result:** Training on 30 days = 432K rows (30d × 24h × 60m × 10 endpoints), takes 60 seconds, MongoDB storage = 500MB

**What Changed:**
- Query now aggregates to per-minute averages per endpoint
- Dimensions changed from raw `response_time` to `avg_response_time`
- 2500× data reduction (1.5B → 432K rows)
- 45× faster training (45 min → 60 sec)

**What Stayed the Same:**
- ✅ Bucket profile logic (business hours, weekends, holidays)
- ✅ BucketResolver determines context from `time_bucket` timestamp
- ✅ trained_models has separate baselines per bucket_key
- ✅ Detection compares current minute's average against bucket baseline
- ✅ Anomaly signal preserved (sudden spike in avg response time detected)

---

## SECTION 11: PERFORMANCE OPTIMIZATION FOR LARGE-SCALE DEPLOYMENTS

### 11.1 Scale Benchmarks & Bottleneck Analysis

**Real-World Test Case:**
- Data Volume: 100M log entries/day
- Retention: 30 days = 3B rows
- Dimensions: 10 metrics
- Training Frequency: Weekly

**Training Pipeline Breakdown (Time %):**
```
Elasticsearch Query:        85% (critical bottleneck)
Network Transfer:            8%
MongoDB Staging:             4%
Bucket Resolution:           2%
Algorithm Computation:       1%
```

**Key Insight:** Optimizing Elasticsearch queries yields 10-100× performance gains.

---

### 10.2 Query Optimization Strategies

#### Strategy 1: Pre-Aggregated Queries (Recommended for >1M rows)

```json
// KB Config
{
  "elasticsearch_sql_query": "SELECT DATE_TRUNC('minute', @timestamp) as ts, SUM(CASE WHEN status=200 THEN 1 ELSE 0 END) as status_200, SUM(CASE WHEN status=404 THEN 1 ELSE 0 END) as status_404 FROM logs WHERE @timestamp >= '$from' AND @timestamp < '$to' GROUP BY ts ORDER BY ts",
  "query_returns_aggregated": true  // Tells Dispatcher: data already grouped
}
```

**Impact:**
- Rows returned: 43,200 (30 days × 1440 min) vs 3B raw rows
- Query time: 2 seconds vs 60 seconds
- **Result: 30× faster training**

**When to use:**
- ✅ Data volume >1M rows
- ✅ Minute/hour-level granularity acceptable
- ✅ Dimensions are counters/sums
- ❌ NOT for: Raw event analysis (e.g., "find anomalous individual requests")

#### Strategy 2: Incremental Training (Rolling Window)

```json
{
  "scheduling": {
    "training_config": {
      "type": "rolling",
      "rolling_settings": {
        "window_size": "7d",  // Train on last 7 days only
        "incremental_update": true,  // Update existing model instead of retraining
        "cron_expression": "0 0 * * 0"  // Weekly
      }
    }
  }
}
```

**Incremental Update Algorithm:**
```python
def incremental_train(new_data, existing_model):
    # Weighted average approach
    n_old = existing_model['sample_size']
    n_new = len(new_data)
    n_total = n_old + n_new
    
    # Update mean
    mean_new = (existing_model['mean'] * n_old + sum(new_data)) / n_total
    
    # Update std (using Welford's algorithm for numerical stability)
    # ... implementation details ...
    
    return {
        "mean": mean_new,
        "std": std_new,
        "sample_size": n_total,
        "last_trained": now()
    }
```

**Impact:**
- Training data: 7 days vs 30 days = 75% reduction
- Works best with stationary data (traffic patterns don't change drastically)

---

### 10.3 Infrastructure Scaling Patterns

#### Pattern 1: KB Sharding by Time Range

For very large datasets, split training across time ranges:

```json
// KB 1: Recent data (high frequency training)
{
  "name": "HTTP Status - Recent",
  "scheduling": {
    "training_config": {
      "static_settings": {
        "from": "2025-11-15T00:00:00Z",  // Last 2 weeks
        "to": "2025-11-29T00:00:00Z"
      }
    }
  },
  "weight": 0.7  // Higher weight in ensemble
}

// KB 2: Historical baseline (low frequency training)
{
  "name": "HTTP Status - Historical",
  "scheduling": {
    "training_config": {
      "static_settings": {
        "from": "2025-10-01T00:00:00Z",  // Older data
        "to": "2025-11-14T00:00:00Z"
      }
    }
  },
  "weight": 0.3  // Lower weight
}
```

**Detection uses weighted ensemble:**
```python
anomaly_score = (score_recent * 0.7) + (score_historical * 0.3)
```

#### Pattern 2: Dimension Sampling (For exploratory analysis)

```json
{
  "algorithm": {
    "name": "zscore",
    "parameters": [
      {"dimension": "status_200", "sample_rate": 0.1},  // Train on 10% of data
      {"dimension": "status_404", "sample_rate": 1.0},  // Critical: use all data
      {"dimension": "status_500", "sample_rate": 1.0}
    ]
  }
}
```

**Use case:** Exploratory phase before full deployment.

---

### 10.4 MongoDB Performance Considerations

#### Index Strategy

```javascript
// staging_buckets collection
db.staging_buckets.createIndex({ job_id: 1, kb_id: 1, dimension: 1, bucket_key: 1 })
db.staging_buckets.createIndex({ created_at: 1 }, { expireAfterSeconds: 86400 })  // TTL

// trained_models collection  
db.trained_models.createIndex({ kb_id: 1, dimension: 1, bucket_key: 1 }, { unique: true })
db.trained_models.createIndex({ last_trained: 1 })  // For incremental updates

// series collection (temporary buffer)
db.series.createIndex({ "metadata.job_id": 1, "metadata.kb_id": 1 })
db.series.createIndex({ "metadata.mode": 1, timestamp: 1 })
```

#### Write Optimization: Bulk Operations

```python
# Dispatcher: Stage data with buckets
operations = []
for record in series_data:
    bucket_key = resolver.resolve(record['timestamp'])
    operations.append(
        UpdateOne(
            {"job_id": job_id, "kb_id": kb_id, "dimension": dimension, "bucket_key": bucket_key},
            {"$push": {"values": record['value']}, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True
        )
    )
    
    # Execute in batches of 1000
    if len(operations) >= 1000:
        mongo_db.staging_buckets.bulk_write(operations, ordered=False)
        operations = []
```

**Impact:** 10-20× faster than individual writes.

---

### 10.5 Elasticsearch Query Best Practices

```sql
-- ❌ BAD: Full table scan with wildcard
SELECT * FROM logs WHERE message LIKE '%error%'

-- ✅ GOOD: Use indexed fields + time range
SELECT @timestamp, status, response_time
FROM logs
WHERE @timestamp >= '$from' 
  AND @timestamp < '$to'
  AND status >= 400  -- Indexed field

-- ✅ BETTER: Pre-aggregate + filter
SELECT 
  DATE_TRUNC('minute', @timestamp) as ts,
  COUNT(*) as total_requests,
  SUM(CASE WHEN status>=500 THEN 1 ELSE 0 END) as error_count
FROM logs
WHERE @timestamp >= '$from' AND @timestamp < '$to'
GROUP BY ts
HAVING error_count > 0  -- Filter at query time
```

---

### 10.6 Caching Strategy (REVISED - No Cross-KB Caching)

**Original Problem:** Assumed batch training of all KBs simultaneously.

**Reality:** Users create KBs ad-hoc, training happens independently.

**Solution: No Caching Needed**

```java
// SIMPLE: Each KB trains independently
public void runTraining(KbMongo kb) {
    UUID jobId = UUID.randomUUID();
    
    String query = kb.getElasticsearchSqlQuery()
        .replace("$from", getTrainingFrom(kb))
        .replace("$to", getTrainingTo(kb));
    
    List<Map<String, Object>> results = elasticsearchService.query(query);
    saveToSeries(results, kb, jobId);
    triggerDispatcher(kb.getId(), jobId);
}
```

**Why no caching?**
- ✅ Simpler code (no cache invalidation logic)
- ✅ No stale data risk
- ✅ Each KB fully independent
- ⚠️ Query duplication if users create identical KBs (acceptable tradeoff for flexibility)

**User guidance:** If multiple KBs need same data, use unified KB with multiple dimensions.

---

### 10.7 Performance Monitoring & Alerting

**Add to KB Config:**
```json
{
  "performance_thresholds": {
    "max_training_duration_seconds": 300,  // Alert if >5 min
    "max_query_rows": 10000000,  // Alert if query returns >10M rows
    "min_sample_size_per_bucket": 100  // Warn if bucket has <100 samples
  }
}
```

**Dispatcher Logging:**
```python
training_metadata = {
    "query_duration_ms": 8500,
    "rows_processed": 2500000,
    "buckets_created": 24,
    "dimensions_trained": 10,
    "total_duration_seconds": 12
}

# Save to trained_models for observability
mongo_db.trained_models.update_one(
    {...},
    {"$set": {"training_metadata": training_metadata}}
)

# Alert if thresholds exceeded
if training_metadata['total_duration_seconds'] > kb['performance_thresholds']['max_training_duration_seconds']:
    send_alert(f"Training took {training_metadata['total_duration_seconds']}s (threshold: 300s)")
```

---

### 10.8 Recommended Configuration by Scale

| Data Volume | Query Strategy | Training Window | Detection Frequency | Expected Training Time |
|-------------|----------------|-----------------|---------------------|----------------------|
| <100K rows | Raw query | 30 days | */5 * * * * | <10 seconds |
| 100K-1M rows | Raw query | 14 days | */5 * * * * | 10-30 seconds |
| 1M-10M rows | Aggregated (minute) | 7 days | */15 * * * * | 30-60 seconds |
| 10M-100M rows | Aggregated (minute) | 7 days (incremental) | */30 * * * * | 1-2 minutes |
| >100M rows | Aggregated (hour) | 7 days (incremental + sampling) | */60 * * * * | 2-5 minutes |

---

## SECTION 8: FINAL RECOMMENDATIONS

### MUST-FIX BEFORE IMPLEMENTATION (Blocking Issues)

1. **[CRITICAL]** Clarify `kb_id` vs `_id` vs `name` usage throughout spec
2. **[CRITICAL]** Resolve collection naming (`trained_models` vs `series_result`)
3. **[CRITICAL]** Decide on BucketResolver execution location (Java vs Python) → **RESOLVED: Python Dispatcher**
4. **[CRITICAL]** Fix overnight shift boundary bug (Test C.1)
5. **[CRITICAL]** Fix exception collision bug (Test E.3)
6. **[CRITICAL - RESOLVED]** Define "1 algorithm per KB" dimension policy → **1 KB = 1 Query = Multiple Dimensions**
7. **[HIGH]** Implement job_id tracking for ETL concurrency
8. **[HIGH]** Replace TTL with explicit cleanup for `staging_buckets`
9. **[HIGH]** Enforce mandatory `query_mode` with `timestamp_field` validation
10. **[HIGH]** Add `is_active` field to algorithm parameters for dimension-level control

### SHOULD-FIX (High Impact, Non-Blocking)

11. **[MEDIUM]** Add rolling training support OR mark as Phase 2
12. **[MEDIUM]** Validate timezone field with IANA database
13. **[MEDIUM]** Add error handling for partial ETL failures
14. **[MEDIUM]** Document detection_window semantics (overlapping windows?)
15. **[MEDIUM - NEW]** Implement incremental training for rolling windows (performance critical at scale)
16. **[MEDIUM - NEW]** Add performance thresholds and monitoring to KB config

### NICE-TO-HAVE (Future Enhancements)

13. **[LOW]** Add bucket profile versioning (profile_v1, profile_v2)
14. **[LOW]** Implement profile A/B testing framework
15. **[LOW]** Add bucket usage analytics (which buckets match most often?)
16. **[LOW]** Support lunar calendar beyond Chinese New Year (Islamic, Hebrew)

---

## SECTION 9: SPECIFICATION QUALITY ASSESSMENT

### Strengths ✅
- **Comprehensive test suite** (Categories A-E cover edge cases)
- **Clear data models** with MongoDB schemas
- **Explicit priority rules** (Exceptions > Schedule > Fallback)
- **Excellent naming** (semantic bucket keys are self-documenting)
- **Proper timezone handling** (crucial for global deployments)

### Weaknesses ❌
- **Assumes greenfield implementation** (no migration path from current system)
- **Python-only code samples** (Java Extractor integration ignored)
- **Missing concurrency details** (job_id usage is mentioned but not enforced)
- **No rollback/cleanup strategy** for failed ETL runs
- **Detection phase vaguely specified** (how does CRON detection work exactly?)

### Overall Grade: **B+ (85/100)**
**Deductions:**
- -5 points: Integration gaps with Java Extractor
- -5 points: Incomplete detection phase design
- -3 points: Collection naming conflicts
- -2 points: Missing error handling specifications

---

## CONCLUSION

This specification provides a **solid conceptual foundation** for context-aware bucketing. The `BucketResolver` design is **well-architected** and the test suite is **rigorous**. However, **significant engineering effort** is required to adapt it to the existing multi-language, change-stream-based architecture.

**Primary Risk:** Underestimating the Java Extractor rewrite scope. The current ETL pipeline is tightly coupled to the old model, and the spec assumes a Python-centric implementation.

**Mitigation Strategy:**
1. Implement BucketResolver as **standalone Python microservice**
2. Keep Java Extractor minimal (just extract + save to `series`)
3. Add new **Python ETL Orchestrator** that bridges Extractor → Bucketing → Training
4. Run pilot with ONE existing KB to validate accuracy improvements

**Approval Status:** ✅ **CONDITIONALLY APPROVED**  
Proceed with Phase 1-2 (BucketResolver + tests), then review before Phase 3 (ETL rewrite).

---

**END OF TECHNICAL REVIEW** (from Claude Sonnet 4.5)

**Start of Final Critique Decision**

This is an exceptionally high-quality review. It accurately identifies the friction points between the ideal "Greenfield" Python specification and the "Brownfield" reality of the Java/Python hybrid architecture.

Here is my **"Critique Back" (Architecture Decision Record)**. This document accepts 95% of your findings, refines the implementation strategy, and establishes the final roadmap.

---

# ARCHITECTURE DECISION RECORD (ADR)
**Topic:** Integration of Dynamic Bucketing into Legacy Java/Python Stack
**Status:** Decided
**Date:** November 24, 2025

## 1. Response to Critical Nomenclature & ID Mismatches

**Verdict:** **ACCEPTED**

*   **KB IDs:** We will strictly use the MongoDB `_id` (ObjectId) as the canonical reference. The Pydantic models in the Python Dispatcher will be updated to map `id` (str) to `_id` (ObjectId) to ensure compatibility with the Java entities.
*   **Collection Strategy:**
    *   We will **NOT** rename `series` to `raw_data_collection`. We will keep `series` to minimize migration risk for existing data.
    *   We **WILL** rename `series_result` to `trained_models` moving forward. This is a necessary semantic shift (Results vs Models).
    *   We **WILL** adopt the singular `algorithm` field structure, deprecating the list format immediately.

## 2. Response to Architectural Integration (The ETL Pivot)

**Verdict:** **ACCEPTED WITH MODIFICATION**

The review correctly identifies that the Java Extractor cannot easily run Python logic (`BucketResolver`).

*   **The Decision:** We will adopt **Option C (Python-Side Resolution)**.
    1.  **Java Extractor:** Remains "Dumb." It simply executes the SQL, validates the timestamp, and dumps raw (or pre-aggregated) data into the `series` collection.
    2.  **Python Dispatcher:** Becomes the "Smart" ETL engine. It will read from `series`, instantiate the `BucketResolver`, perform the staging into `staging_buckets`, and execute training.
*   **Why:** Porting the complex "Friday Night Party" / "Lunar Holiday" logic to Java would duplicate code and introduce drift risk. Python is better suited for this logic.

## 3. Response to Detection Strategy (Event vs. Scheduled)

**Verdict:** **ACCEPTED (Major Pivot)**

The critique highlights that Context-Aware Detection is inherently time-based, not event-based.

*   **The Decision:** We are **abandoning MongoDB Change Streams** for the Detection phase of *this specific feature*.
*   **The New Flow:** We will implement the **Micro-Batch Detection Pattern**.
    *   A Java Scheduler (CRON) triggers the Python Dispatcher every $N$ minutes.
    *   Python calculates the *current* bucket key (e.g., `business_hours_14`).
    *   Python queries the *last N minutes* of data (Aggregated or Raw) directly from Elasticsearch or the `series` buffer.
    *   Python compares against the `trained_model`.

## 4. Response to "Raw vs. Aggregated" Modes (Section 10)

**Verdict:** **STRONGLY ACCEPTED**

This is the missing link for scalability. The specification in Section 10 of the review is approved as the **Canonical Design**.

*   **Implementation:** We will enforce the `query_mode` configuration.
*   **Validation:** The `timestamp_field` validation logic is mandatory. We cannot rely on implicit `@timestamp` assumptions anymore.

## 5. Response to Testing & Quality Gates

**Verdict:** **ACCEPTED**

*   **Environment:** We will include the `os.environ['TZ']` fixture.
*   **Logic Bug:** The overwrite bug in `_precompute_exceptions` (Test E.3) is acknowledged. The code must check `if date not in lookup_map` before assigning to ensure priority is respected.
*   **Overnight Bug:** The Off-By-One error (`<=` vs `<`) in overnight logic is acknowledged and will be fixed.

---

## REVISED ACTION PLAN

Based on your review, here is the corrected execution order. I am requesting the Development Agent to follow this specific sequence:

### Phase 1: The Logic Core (Python)
1.  Implement `BucketProfile` and `KBConfig` Pydantic models (fixing the ID/Singular Algo issues).
2.  Implement `BucketResolver` with the logic fixes (Overnight `<` fix, Exception Priority fix).
3.  Implement the **Test Suite** (Categories A-E) including the Timezone fixtures.

### Phase 2: The Java/Python Bridge
1.  Update Java `KbMongo` entity to support `bucket_profile_id` and `query_mode`.
2.  Update Java Extractor to validate `timestamp_field` and support the Unified Query format.
3.  **Critical:** Ensure Java saves data to `series` with a consistent normalized `timestamp` field, regardless of the source column name.

### Phase 3: The Training ETL (Python)
1.  Implement the `staging_buckets` logic.
2.  Implement the `job_id` concurrency logic.
3.  Implement the **Dual-Mode Training** (Raw vs Aggregated) logic.
    *   *Note:* The Python code doesn't actually change much here; it just processes fewer, heavier rows in Aggregated mode.

### Phase 4: The Detection Switch
1.  Implement the Java `DetectionSchedulerService`.
2.  Connect it to the Python Dispatcher's new `run_detection_batch` endpoint.

---

Here is the **Finalized Master Implementation Plan**. It incorporates the Context-Aware Logic, the Raw/Aggregated Training Modes, and the Scalable Micro-Batch Detection architecture.

***

# ARCHITECTURE REVIEW: SCALABILITY & HIGH-FREQUENCY DETECTION
**Review Date:** November 24, 2025
**Review Target:** Section 11 (Proposed by AI)
**Context:** Integration with decided "Java Extractor + Python Dispatcher" Architecture

---

## EXECUTIVE SUMMARY

The proposed **Section 11** correctly identifies the massive scalability risks introduced by "1-second detection" and "Multi-KB" environments. The logic regarding the **Thundering Herd** problem and **Deterministic Offsets** is excellent and should be adopted immediately.

However, the proposal introduces **three critical architectural conflicts** with our previously established decisions:
1.  **Process Management:** It suggests spawning Python processes *inside* API requests (dangerous).
2.  **Query Strategy:** It suggests `UNION ALL` for Elasticsearch, which is inefficient/unsupported compared to `_msearch`.
3.  **Frequency Reality:** It validates "1-second detection" via polling, which effectively turns our anomaly detection system into a Denial-of-Service (DoS) attack against the user's Elasticsearch cluster.

**Assessment:** ✅ **PARTIALLY ACCEPTED**
**Status:** Adopt the **Offset Logic** and **Caching**. Reject the **Process Spawning** and **SQL Batching** in favor of standard Elastic patterns.

---

## 1. CRITIQUE: THE "1-SECOND DETECTION" FALLACY

### The Proposal's Claim
> "100 KBs with 1-second detection is achievable... Elasticsearch query (Java Extractor) 200-500ms."

### The Critique
While mathematically possible on paper, implementing **1-second polling** against Elasticsearch is architecturally irresponsible.
1.  **Elasticsearch Refresh Interval:** By default, ES indexes refresh every 1 second. Querying every second guarantees you are hitting the cluster at the exact moment it is trying to write/index segments.
2.  **Network Overhead:** Opening/Closing HTTP connections every second for 100 KBs creates massive overhead.
3.  **The "Observer Effect":** The monitoring tool becomes the heaviest load on the system it is monitoring.

### The Correction
We must enforce a **Hard Floor** on detection frequency based on the `query_mode`:
*   **RAW Mode:** Minimum 1 minute (due to query cost).
*   **AGGREGATED Mode:** Minimum 10 seconds (never 1 second).
*   *If a user needs sub-second detection, they need a Stream Processor (Flink/Kafka), not a Batch Poller.*

---

## 2. CRITIQUE: PYTHON MULTIPROCESSING INSIDE API

### The Proposal's Approach
```python
# Inside FastAPI Endpoint
with Pool(processes=min(cpu_count(), len(kb_ids))) as pool:
    results = pool.map(detect_single_kb, kb_ids)
```

### The Critique
Spawning a `multiprocessing.Pool` **inside an HTTP Request Handler** is an anti-pattern in production web services (Uvicorn/Gunicorn).
1.  **Zombie Processes:** If the HTTP request times out or is cancelled, child processes can become orphaned.
2.  **Memory Explosion:** Forking the process copies the parent's memory space. Doing this 100 times/sec (for high frequency) causes high GC churn.
3.  **Context Switching:** The overhead of spinning up a pool often exceeds the execution time of a lightweight calculation like Z-Score.

### The Correction
Since we decided that **Python performs the Detection Query** (ADR Point 3), the bottleneck is **I/O** (waiting for Elastic), not **CPU** (calculating Z-score).
*   **Solution:** Use **AsyncIO** (`await elastic.search(...)`).
*   Python handles thousands of concurrent I/O waits on a single thread. No need for multiprocessing complexity.

---

## 3. CRITIQUE: `UNION ALL` VS `_msearch`

### The Proposal's Approach
> "Single UNION ALL query... SELECT 'kb_1'... UNION ALL SELECT 'kb_2'..."

### The Critique
Elasticsearch SQL's support for `UNION ALL` is limited and computationally expensive because it effectively runs separate searches and merges them in the coordinator node. It also complicates parsing (mapping dynamic columns from different KBs into a single schema).

### The Correction
Use the native Elasticsearch **Multi-Search API (`_msearch`)**.
*   **Efficiency:** Designed specifically for this "Send 50 queries at once" use case.
*   **Isolation:** If one query fails (syntax error), the others still return.
*   **Parsing:** Returns a list of separate responses, making mapping back to `kb_id` trivial.

---

## 4. CRITIQUE: SCALABILITY TIERS

### Tier 1: Detection Offset (Thundering Herd)
**Verdict:** ⭐ **EXCELLENT / ACCEPT.**
The hash-based offset (`hash(kb_id) % interval`) is the perfect stateless solution.
*   *Refinement:* Ensure the Java Scheduler calculates this offset once at startup, not every tick.

### Tier 2: Batching
**Verdict:** **MODIFY.**
Do not implement `UNION ALL`. Implement `_msearch` batching.
*   **Java Extractor Role:** Groups KBs that need detection *now*.
*   **Python Dispatcher Role:** Receives a list of `[KB_Config]`. Constructs one `_msearch` payload. Awaits response. Runs vector Z-Score on results.

### Tier 3: Redis/Celery
**Verdict:** **DEFER.**
For the MVP/V1, HTTP communication between Java and Python is sufficient if we use Batching (`_msearch`). Adding a Message Broker now increases deployment complexity (requires Redis) for a problem we haven't hit yet.

---

## REVISED IMPLEMENTATION PLAN (For Section 11)

### 11.1 The "Micro-Batch" Detection Logic (Revised)

**Java Extractor (The Clock):**
1.  **Scheduler Loop:** Runs every 1 second (high resolution).
2.  **Candidate Selection:** Finds all KBs where `next_run_time <= now`.
    *   *Offset Logic:* `next_run_time` is calculated using the deterministic hash offset.
3.  **Batching:** Groups up to 50 KBs into a single `DetectionBatchRequest`.
4.  **Dispatch:** Sends HTTP POST `python-service/detect/batch` with the list of Configs.

**Python Dispatcher (The Worker):**
1.  **Endpoint:** `async def detect_batch(kbs: List[KBConfig])`.
2.  **Context Resolution:**
    *   Iterates KBs.
    *   Calls `resolver.resolve(now)` for each.
3.  **Baseline Fetching (Cached):**
    *   `get_cached_models(kb_ids, bucket_keys)`.
    *   *Optimization:* Fetch all required models from Mongo in one `$in` query if not in RAM cache.
4.  **Data Fetching (Async I/O):**
    *   Constructs Elastic `_msearch` body.
    *   `responses = await es_client.msearch(body=...)`
5.  **Compute:**
    *   Iterates responses.
    *   Calculates Z-Score/Anomaly.
6.  **Response:** Returns list of anomalies to Java (or writes directly to ES Anomaly Index).

---

### 11.2 Required Validations (Add to Spec)

1.  **Minimum Frequency Validator:**
    *   KB Config must reject `frequency < 10s` for Aggregated Mode.
    *   KB Config must reject `frequency < 1m` for Raw Mode.
2.  **Baseline LRU Cache:**
    *   Python must cache `trained_models` in memory for 5-10 minutes. Reading Mongo every second for the same baseline is wasteful.

---

### 11.3 Final Recommendation to User

**Do not paste the previous AI's Section 11 directly.** It contains implementation details (Multiprocessing, UNION ALL) that conflict with best practices for your specific stack.

**Instead, use this condensed strategy:**
1.  **Adopt Deterministic Offsets** to solve Thundering Herd.
2.  **Adopt `_msearch`** for batching queries (instead of SQL UNION).
3.  **Adopt AsyncIO** in Python (instead of Multiprocessing).
4.  **Enforce Minimum Frequency Limits** to protect the database.