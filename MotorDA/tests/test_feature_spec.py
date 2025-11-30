#!/usr/bin/env python3
"""Feature Specification Test Suite for BucketResolver"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys
sys.path.insert(0, '/app')
from Dispatcher.bucket_resolver import BucketResolver

def check(test_name, actual, expected):
    status = "PASS" if actual == expected else "FAIL"
    print(f"  {test_name}: {actual} (expected: {expected}) - {status}")
    return status == "PASS"

print("=" * 60)
print("FEATURE SPECIFICATION TEST SUITE")
print("=" * 60)

passed = 0
total = 0

# Test A.1: Daily Bucket Strategy
print("\n--- Test A.1: Daily Bucket Strategy ---")
profile = {
    '_id': 'test_daily',
    'timezone': 'America/New_York',
    'schedule': [
        {'bucket_base_key': 'monday', 'days': [1], 'time_range': {'start': '00:00', 'end': '23:59'}, 'granularity': 'block'},
        {'bucket_base_key': 'tuesday', 'days': [2], 'time_range': {'start': '00:00', 'end': '23:59'}, 'granularity': 'block'},
    ],
    'fallback': {'bucket_base_key': 'other', 'granularity': 'block'}
}
resolver = BucketResolver.from_dict(profile)

ts = datetime(2025, 12, 1, 19, 0, 0, tzinfo=ZoneInfo('UTC'))  # Dec 1 is Monday, 14:00 EST
total += 1; passed += check("Monday 14:00", resolver.resolve(ts), "monday")

ts = datetime(2025, 12, 2, 4, 59, 0, tzinfo=ZoneInfo('UTC'))  # Monday 23:59 EST
total += 1; passed += check("Monday 23:59", resolver.resolve(ts), "monday")

ts = datetime(2025, 12, 2, 5, 1, 0, tzinfo=ZoneInfo('UTC'))  # Tuesday 00:01 EST
total += 1; passed += check("Tuesday 00:01", resolver.resolve(ts), "tuesday")

# Test A.2: Global Hourly Strategy
print("\n--- Test A.2: Global Hourly Strategy ---")
profile = {
    '_id': 'test_global_hourly',
    'timezone': 'America/New_York',
    'schedule': [
        {'bucket_base_key': 'global', 'days': [1,2,3,4,5,6,7], 'time_range': {'start': '00:00', 'end': '23:59'}, 'granularity': 'hourly'},
    ],
    'fallback': {'bucket_base_key': 'fallback', 'granularity': 'hourly'}
}
resolver = BucketResolver.from_dict(profile)

ts = datetime(2025, 12, 1, 19, 15, 0, tzinfo=ZoneInfo('UTC'))  # Monday 14:15 EST
total += 1; passed += check("Monday 14:15", resolver.resolve(ts), "global_14")

ts = datetime(2025, 11, 30, 19, 45, 0, tzinfo=ZoneInfo('UTC'))  # Sunday 14:45 EST
total += 1; passed += check("Sunday 14:45", resolver.resolve(ts), "global_14")

# Test A.3: Workday vs Weekend Hourly
print("\n--- Test A.3: Workday vs Weekend Hourly ---")
profile = {
    '_id': 'test_workday_weekend',
    'timezone': 'America/New_York',
    'schedule': [
        {'bucket_base_key': 'workday', 'days': [1,2,3,4,5], 'time_range': {'start': '00:00', 'end': '23:59'}, 'granularity': 'hourly'},
        {'bucket_base_key': 'weekend', 'days': [6,7], 'time_range': {'start': '00:00', 'end': '23:59'}, 'granularity': 'hourly'},
    ],
    'fallback': {'bucket_base_key': 'fallback', 'granularity': 'hourly'}
}
resolver = BucketResolver.from_dict(profile)

ts = datetime(2025, 12, 1, 14, 0, 0, tzinfo=ZoneInfo('UTC'))  # Monday 09:00 EST
total += 1; passed += check("Monday 09:00", resolver.resolve(ts), "workday_09")

ts = datetime(2025, 11, 29, 14, 0, 0, tzinfo=ZoneInfo('UTC'))  # Saturday 09:00 EST
total += 1; passed += check("Saturday 09:00", resolver.resolve(ts), "weekend_09")

# Test A.4: Active vs Quiet Intra-Day
print("\n--- Test A.4: Active vs Quiet Intra-Day ---")
profile = {
    '_id': 'test_active_quiet',
    'timezone': 'America/New_York',
    'schedule': [
        {'bucket_base_key': 'active', 'days': [1,2,3,4,5,6,7], 'time_range': {'start': '09:00', 'end': '17:00'}, 'granularity': 'hourly'},
        {'bucket_base_key': 'quiet', 'days': [1,2,3,4,5,6,7], 'time_range': {'start': '17:01', 'end': '08:59'}, 'granularity': 'block'},
    ],
    'fallback': {'bucket_base_key': 'fallback', 'granularity': 'block'}
}
resolver = BucketResolver.from_dict(profile)

ts = datetime(2025, 11, 29, 19, 30, 0, tzinfo=ZoneInfo('UTC'))  # 14:30 EST
total += 1; passed += check("14:30 EST", resolver.resolve(ts), "active_14")

ts = datetime(2025, 11, 29, 7, 30, 0, tzinfo=ZoneInfo('UTC'))  # 02:30 EST
total += 1; passed += check("02:30 EST", resolver.resolve(ts), "quiet")

# Test B.1: Lunch Break Override
print("\n--- Test B.1: Lunch Break Override ---")
profile = {
    '_id': 'test_lunch',
    'timezone': 'America/New_York',
    'schedule': [
        {'bucket_base_key': 'lunch', 'days': [1,2,3,4,5], 'time_range': {'start': '12:00', 'end': '13:00'}, 'granularity': 'block'},
        {'bucket_base_key': 'workday', 'days': [1,2,3,4,5], 'time_range': {'start': '09:00', 'end': '17:00'}, 'granularity': 'hourly'},
    ],
    'fallback': {'bucket_base_key': 'fallback', 'granularity': 'hourly'}
}
resolver = BucketResolver.from_dict(profile)

ts = datetime(2025, 12, 2, 17, 30, 0, tzinfo=ZoneInfo('UTC'))  # Tuesday 12:30 EST
total += 1; passed += check("Tue 12:30 (lunch)", resolver.resolve(ts), "lunch")

# Test B.2: Holiday Override
print("\n--- Test B.2: Holiday Override ---")
profile = {
    '_id': 'test_holiday',
    'timezone': 'America/New_York',
    'exceptions': [
        {'bucket_base_key': 'xmas', 'rule': {'month': 12, 'day': 25}, 'granularity': 'block'},
    ],
    'schedule': [
        {'bucket_base_key': 'workday', 'days': [1,2,3,4,5], 'time_range': {'start': '00:00', 'end': '23:59'}, 'granularity': 'hourly'},
    ],
    'fallback': {'bucket_base_key': 'fallback', 'granularity': 'hourly'}
}
resolver = BucketResolver.from_dict(profile)

ts = datetime(2025, 12, 25, 15, 0, 0, tzinfo=ZoneInfo('UTC'))  # Xmas 10:00 EST
total += 1; passed += check("Dec 25 (holiday)", resolver.resolve(ts), "xmas")

# Test C.1: Friday Night Party (Overnight Lookback)
print("\n--- Test C.1: Friday Night Party (Overnight) ---")
profile = {
    '_id': 'test_overnight',
    'timezone': 'America/New_York',
    'schedule': [
        {'bucket_base_key': 'party_shift', 'days': [5], 'time_range': {'start': '20:00', 'end': '04:00'}, 'granularity': 'block'},
    ],
    'fallback': {'bucket_base_key': 'fallback', 'granularity': 'hourly'}
}
resolver = BucketResolver.from_dict(profile)

# Nov 28 is Friday, Nov 29 is Saturday
# Friday 21:00 EST should be party_shift
ts = datetime(2025, 11, 29, 2, 0, 0, tzinfo=ZoneInfo('UTC'))  # Friday 21:00 EST
total += 1; passed += check("Friday 21:00", resolver.resolve(ts), "party_shift")

# Saturday 02:00 EST should also be party_shift (overnight lookback)
ts = datetime(2025, 11, 29, 7, 0, 0, tzinfo=ZoneInfo('UTC'))  # Saturday 02:00 EST
total += 1; passed += check("Saturday 02:00 (overnight)", resolver.resolve(ts), "party_shift")

# Saturday 04:00 EST should NOT be party_shift (exclusive end)
ts = datetime(2025, 11, 29, 9, 0, 0, tzinfo=ZoneInfo('UTC'))  # Saturday 04:00 EST
total += 1; passed += check("Saturday 04:00 (end)", resolver.resolve(ts), "fallback_04")

# Test D.1: Naming Sanitization
print("\n--- Test D.1: Naming Sanitization ---")
profile = {
    '_id': 'test_sanitize',
    'timezone': 'UTC',
    'schedule': [
        {'bucket_base_key': 'My Super Campaign! (2025)', 'days': [1,2,3,4,5,6,7], 'time_range': {'start': '00:00', 'end': '23:59'}, 'granularity': 'block'},
    ],
    'fallback': {'bucket_base_key': 'fallback', 'granularity': 'block'}
}
resolver = BucketResolver.from_dict(profile)
ts = datetime(2025, 11, 29, 12, 0, 0, tzinfo=ZoneInfo('UTC'))
total += 1; passed += check("Messy name", resolver.resolve(ts), "my_super_campaign_2025")

# Test D.2: Timezone Math
print("\n--- Test D.2: Timezone Math ---")
profile = {
    '_id': 'test_tz',
    'timezone': 'America/New_York',
    'schedule': [
        {'bucket_base_key': 'match', 'days': [1,2,3,4,5,6,7], 'time_range': {'start': '09:00', 'end': '09:59'}, 'granularity': 'block'},
    ],
    'fallback': {'bucket_base_key': 'no_match', 'granularity': 'block'}
}
resolver = BucketResolver.from_dict(profile)
ts = datetime(2025, 11, 29, 14, 0, 0, tzinfo=ZoneInfo('UTC'))  # 14:00 UTC = 09:00 EST
total += 1; passed += check("14:00 UTC = 09:00 EST", resolver.resolve(ts), "match")

# Test D.3: Null Profile (Global Fallback)
print("\n--- Test D.3: Null Profile (Global Fallback) ---")
resolver = BucketResolver.from_dict(None)
ts = datetime(2025, 11, 29, 12, 0, 0, tzinfo=ZoneInfo('UTC'))
total += 1; passed += check("Null profile", resolver.resolve(ts), "global_default")

# Test E.2: Exact Boundary
print("\n--- Test E.2: Exact Boundary ---")
profile = {
    '_id': 'test_boundary',
    'timezone': 'America/New_York',
    'schedule': [
        {'bucket_base_key': 'active', 'days': [1,2,3,4,5,6,7], 'time_range': {'start': '09:00', 'end': '17:00'}, 'granularity': 'block'},
    ],
    'fallback': {'bucket_base_key': 'inactive', 'granularity': 'block'}
}
resolver = BucketResolver.from_dict(profile)
ts = datetime(2025, 11, 29, 22, 0, 0, tzinfo=ZoneInfo('UTC'))  # 17:00 EST (boundary)
total += 1; passed += check("17:00 (boundary)", resolver.resolve(ts), "active")

ts = datetime(2025, 11, 29, 22, 1, 0, tzinfo=ZoneInfo('UTC'))  # 17:01 EST (past boundary)
total += 1; passed += check("17:01 (past)", resolver.resolve(ts), "inactive")

# Test E.3: Exception Collision
print("\n--- Test E.3: Exception Collision ---")
profile = {
    '_id': 'test_collision',
    'timezone': 'America/New_York',
    'exceptions': [
        {'bucket_base_key': 'black_friday', 'rule': {'month': 11, 'day': 28}, 'granularity': 'block'},
        {'bucket_base_key': 'campaign_x', 'rule': {'month': 11, 'day': 28}, 'granularity': 'block'},
    ],
    'fallback': {'bucket_base_key': 'fallback', 'granularity': 'block'}
}
resolver = BucketResolver.from_dict(profile)
ts = datetime(2025, 11, 28, 15, 0, 0, tzinfo=ZoneInfo('UTC'))  # Nov 28
total += 1; passed += check("Nov 28 (first wins)", resolver.resolve(ts), "black_friday")

print("\n" + "=" * 60)
print(f"TEST RESULTS: {passed}/{total} PASSED")
print("=" * 60)
