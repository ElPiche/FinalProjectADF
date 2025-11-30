"""
Test suite for BucketResolver - Dynamic Context-Aware Anomaly Detection
Tests organized by category per Feature Specification Section 6.2-6.6
"""

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from Dispatcher.bucket_resolver import (
    BucketResolver,
    BucketProfile,
    ScheduleRule,
    ExceptionRule,
    FallbackRule,
    sanitize_bucket_key,
    GLOBAL_DEFAULT_KEY,
)


# ==================== CATEGORY A: GRANULARITY & SEGMENTATION ====================

class TestCategoryA_GranularitySegmentation:
    """Category A: Different bucket strategies per spec Section 6.2"""
    
    def test_a1_daily_bucket_strategy(self):
        """A.1: One bucket for each day of the week (block granularity)"""
        profile = BucketProfile(
            profile_id="daily_buckets",
            timezone="UTC",
            schedule=[
                ScheduleRule(bucket_base_key="monday", days=[1], granularity="block"),
                ScheduleRule(bucket_base_key="tuesday", days=[2], granularity="block"),
                ScheduleRule(bucket_base_key="wednesday", days=[3], granularity="block"),
                ScheduleRule(bucket_base_key="thursday", days=[4], granularity="block"),
                ScheduleRule(bucket_base_key="friday", days=[5], granularity="block"),
                ScheduleRule(bucket_base_key="saturday", days=[6], granularity="block"),
                ScheduleRule(bucket_base_key="sunday", days=[7], granularity="block"),
            ],
            fallback=FallbackRule(bucket_base_key="unknown", granularity="block"),
        )
        resolver = BucketResolver(profile)
        
        # Monday 2024-01-15 at 14:00 UTC
        ts_monday = datetime(2024, 1, 15, 14, 0, 0, tzinfo=ZoneInfo("UTC"))
        assert resolver.resolve(ts_monday) == "monday"
        
        # Monday at 23:59 UTC
        ts_monday_late = datetime(2024, 1, 15, 23, 59, 0, tzinfo=ZoneInfo("UTC"))
        assert resolver.resolve(ts_monday_late) == "monday"
        
        # Tuesday at 00:01 UTC
        ts_tuesday = datetime(2024, 1, 16, 0, 1, 0, tzinfo=ZoneInfo("UTC"))
        assert resolver.resolve(ts_tuesday) == "tuesday"
    
    def test_a2_global_hourly_strategy(self):
        """A.2: 24 buckets (00-23) regardless of day of week"""
        profile = BucketProfile(
            profile_id="global_hourly",
            timezone="UTC",
            schedule=[
                ScheduleRule(bucket_base_key="global", days=[1, 2, 3, 4, 5, 6, 7], granularity="hourly"),
            ],
            fallback=FallbackRule(bucket_base_key="fallback", granularity="hourly"),
        )
        resolver = BucketResolver(profile)
        
        # Monday at 14:15
        ts_mon = datetime(2024, 1, 15, 14, 15, 0, tzinfo=ZoneInfo("UTC"))
        assert resolver.resolve(ts_mon) == "global_14"
        
        # Sunday at 14:45
        ts_sun = datetime(2024, 1, 21, 14, 45, 0, tzinfo=ZoneInfo("UTC"))
        assert resolver.resolve(ts_sun) == "global_14"
    
    def test_a3_workday_vs_weekend_hourly_split(self):
        """A.3: Differentiating 9 AM on Monday from 9 AM on Saturday"""
        profile = BucketProfile(
            profile_id="workday_weekend",
            timezone="UTC",
            schedule=[
                ScheduleRule(bucket_base_key="workday", days=[1, 2, 3, 4, 5], granularity="hourly"),
                ScheduleRule(bucket_base_key="weekend", days=[6, 7], granularity="hourly"),
            ],
            fallback=FallbackRule(bucket_base_key="fallback", granularity="hourly"),
        )
        resolver = BucketResolver(profile)
        
        # Monday 09:00
        ts_mon = datetime(2024, 1, 15, 9, 0, 0, tzinfo=ZoneInfo("UTC"))
        assert resolver.resolve(ts_mon) == "workday_09"
        
        # Saturday 09:00
        ts_sat = datetime(2024, 1, 20, 9, 0, 0, tzinfo=ZoneInfo("UTC"))
        assert resolver.resolve(ts_sat) == "weekend_09"
    
    def test_a4_active_vs_quiet_intraday_split(self):
        """A.4: Hourly buckets for business hours, single bucket for night"""
        profile = BucketProfile(
            profile_id="active_quiet",
            timezone="UTC",
            schedule=[
                # Active hours first (higher priority by position)
                ScheduleRule(bucket_base_key="active", days=[1, 2, 3, 4, 5, 6, 7], 
                           start_time="09:00", end_time="17:00", granularity="hourly"),
                # Quiet hours (fallback for times outside active)
            ],
            fallback=FallbackRule(bucket_base_key="quiet", granularity="block"),
        )
        resolver = BucketResolver(profile)
        
        # 14:30 - active hours
        ts_active = datetime(2024, 1, 15, 14, 30, 0, tzinfo=ZoneInfo("UTC"))
        assert resolver.resolve(ts_active) == "active_14"
        
        # 02:30 - quiet hours (fallback)
        ts_quiet = datetime(2024, 1, 15, 2, 30, 0, tzinfo=ZoneInfo("UTC"))
        assert resolver.resolve(ts_quiet) == "quiet"


# ==================== CATEGORY B: PRIORITY & OVERLAPS ====================

class TestCategoryB_PriorityOverlaps:
    """Category B: Waterfall priority per spec Section 6.3"""
    
    def test_b1_lunch_break_override(self):
        """B.1: Specific 'Low Traffic' window inside 'High Traffic' day"""
        profile = BucketProfile(
            profile_id="lunch_override",
            timezone="UTC",
            schedule=[
                # Index 0 (Higher Priority) - Lunch break
                ScheduleRule(bucket_base_key="lunch", days=[1, 2, 3, 4, 5], 
                           start_time="12:00", end_time="13:00", granularity="block"),
                # Index 1 (Lower Priority) - Workday
                ScheduleRule(bucket_base_key="workday", days=[1, 2, 3, 4, 5], 
                           start_time="09:00", end_time="17:00", granularity="hourly"),
            ],
            fallback=FallbackRule(bucket_base_key="off_hours", granularity="block"),
        )
        resolver = BucketResolver(profile)
        
        # Tuesday at 12:30 - should be lunch (not workday)
        ts = datetime(2024, 1, 16, 12, 30, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts)
        assert result == "lunch", f"Expected 'lunch', got '{result}'"
    
    def test_b2_holiday_override(self):
        """B.2: Christmas falls on a Monday - exception takes priority"""
        profile = BucketProfile(
            profile_id="holiday_test",
            timezone="UTC",
            exceptions=[
                ExceptionRule(bucket_base_key="xmas", month=12, day=25, granularity="block"),
            ],
            schedule=[
                ScheduleRule(bucket_base_key="monday_work", days=[1], 
                           start_time="09:00", end_time="17:00", granularity="hourly"),
            ],
            fallback=FallbackRule(bucket_base_key="off_hours", granularity="block"),
        )
        resolver = BucketResolver(profile)
        
        # Christmas 2025 at 10:00 (Thursday, but tested with any date)
        # Use December 25, 2023 which was a Monday
        ts = datetime(2023, 12, 25, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts)
        assert result == "xmas", f"Expected 'xmas', got '{result}'"


# ==================== CATEGORY C: COMPLEX SHIFTS ====================

class TestCategoryC_ComplexShifts:
    """Category C: Overnight & seasonality per spec Section 6.4"""
    
    def test_c1_friday_night_party_overnight_lookback(self):
        """C.1: Shift starts Friday 20:00, ends Saturday 04:00"""
        profile = BucketProfile(
            profile_id="overnight_test",
            timezone="UTC",
            schedule=[
                ScheduleRule(bucket_base_key="party_shift", days=[5], 
                           start_time="20:00", end_time="04:00", granularity="block"),
            ],
            fallback=FallbackRule(bucket_base_key="normal", granularity="block"),
        )
        resolver = BucketResolver(profile)
        
        # Friday 2024-01-19 at 22:00 - within the Friday part of the shift
        ts_friday = datetime(2024, 1, 19, 22, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts_friday)
        assert result == "party_shift", f"Friday 22:00: Expected 'party_shift', got '{result}'"
        
        # Saturday 2024-01-20 at 02:00 - overnight lookback should catch this
        ts_saturday = datetime(2024, 1, 20, 2, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts_saturday)
        assert result == "party_shift", f"Saturday 02:00: Expected 'party_shift', got '{result}'"
    
    def test_c2_winter_month_wrap_around(self):
        """C.2: Rule applies only in Winter (Dec, Jan, Feb)"""
        profile = BucketProfile(
            profile_id="winter_test",
            timezone="UTC",
            schedule=[
                ScheduleRule(bucket_base_key="winter", days=[1, 2, 3, 4, 5, 6, 7], 
                           months=[12, 1, 2], granularity="block"),
            ],
            fallback=FallbackRule(bucket_base_key="normal", granularity="block"),
        )
        resolver = BucketResolver(profile)
        
        # December 31, 2025
        ts_dec = datetime(2025, 12, 31, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        assert resolver.resolve(ts_dec) == "winter"
        
        # January 1, 2026
        ts_jan = datetime(2026, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        assert resolver.resolve(ts_jan) == "winter"
        
        # March 1, 2026 - not winter
        ts_mar = datetime(2026, 3, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        assert resolver.resolve(ts_mar) == "normal"
    
    def test_c3_empty_months_safety(self):
        """C.3: Empty months list should NOT match"""
        profile = BucketProfile(
            profile_id="empty_months_test",
            timezone="UTC",
            schedule=[
                ScheduleRule(bucket_base_key="broken_rule", days=[1, 2, 3, 4, 5, 6, 7], 
                           months=[], granularity="block"),  # Empty list = never match
            ],
            fallback=FallbackRule(bucket_base_key="fallback", granularity="block"),
        )
        resolver = BucketResolver(profile)
        
        # Any date should NOT match broken_rule
        ts = datetime(2024, 6, 15, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts)
        assert result != "broken_rule", "Empty months should never match"
        assert result == "fallback"


# ==================== CATEGORY D: TECHNICAL INTEGRITY ====================

class TestCategoryD_TechnicalIntegrity:
    """Category D: Sanitization & robustness per spec Section 6.5"""
    
    def test_d1_naming_determinism_sanitization(self):
        """D.1: Messy bucket name gets sanitized"""
        result = sanitize_bucket_key("My Super Campaign! (2025)")
        assert result == "my_super_campaign_2025"
        assert " " not in result
        assert "!" not in result
        assert "(" not in result
        assert ")" not in result
        assert result.islower()
    
    def test_d2_timezone_math_utc_vs_local(self):
        """D.2: UTC timestamp converts correctly to local timezone"""
        profile = BucketProfile(
            profile_id="timezone_test",
            timezone="America/New_York",  # EST = UTC-5
            schedule=[
                ScheduleRule(bucket_base_key="business", days=[1, 2, 3, 4, 5], 
                           start_time="09:00", end_time="17:00", granularity="hourly"),
            ],
            fallback=FallbackRule(bucket_base_key="off_hours", granularity="block"),
        )
        resolver = BucketResolver(profile)
        
        # 14:00 UTC = 09:00 EST (should match business hours)
        ts = datetime(2024, 1, 15, 14, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts)
        assert result == "business_09", f"Expected 'business_09', got '{result}'"
    
    def test_d3_global_fallback_null_profile(self):
        """D.3: Null profile returns global_default"""
        resolver = BucketResolver(profile=None)
        
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts)
        assert result == GLOBAL_DEFAULT_KEY


# ==================== CATEGORY E: ADVANCED ROBUSTNESS ====================

class TestCategoryE_AdvancedRobustness:
    """Category E: DST, boundaries, collisions per spec Section 6.6"""
    
    def test_e1_dst_spring_forward_no_crash(self):
        """E.1: DST spring forward - resolver must NOT crash"""
        profile = BucketProfile(
            profile_id="dst_test",
            timezone="America/New_York",
            schedule=[
                ScheduleRule(bucket_base_key="normal", days=[1, 2, 3, 4, 5, 6, 7], granularity="hourly"),
            ],
            fallback=FallbackRule(bucket_base_key="fallback", granularity="hourly"),
        )
        resolver = BucketResolver(profile)
        
        # March 9, 2025 - DST starts (2:00 AM becomes 3:00 AM in NY)
        # UTC time that maps to ~2:30 AM NY (which doesn't exist)
        # 7:30 UTC = 2:30 AM EST (but 3:30 AM EDT after spring forward)
        ts = datetime(2025, 3, 9, 7, 30, 0, tzinfo=ZoneInfo("UTC"))
        
        # Should NOT raise an exception
        try:
            result = resolver.resolve(ts)
            assert result is not None
        except Exception as e:
            pytest.fail(f"Resolver crashed on DST edge case: {e}")
    
    def test_e2_exact_boundary_inclusive_exclusive(self):
        """E.2: Time range start inclusive, end inclusive (minute granularity)"""
        profile = BucketProfile(
            profile_id="boundary_test",
            timezone="UTC",
            schedule=[
                ScheduleRule(bucket_base_key="business", days=[1, 2, 3, 4, 5, 6, 7], 
                           start_time="09:00", end_time="17:00", granularity="hourly"),
            ],
            fallback=FallbackRule(bucket_base_key="off_hours", granularity="block"),
        )
        resolver = BucketResolver(profile)
        
        # 17:00 - should still match (inclusive end at minute granularity)
        ts_1700 = datetime(2024, 1, 15, 17, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts_1700)
        assert result == "business_17", f"17:00 should match, got '{result}'"
        
        # 17:01 - should NOT match
        ts_1701 = datetime(2024, 1, 15, 17, 1, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts_1701)
        assert result == "off_hours", f"17:01 should NOT match, got '{result}'"
    
    def test_e3_exception_collision_first_match_wins(self):
        """E.3: Two exceptions on same date - first match wins"""
        profile = BucketProfile(
            profile_id="collision_test",
            timezone="UTC",
            exceptions=[
                # Index 0 - should win
                ExceptionRule(bucket_base_key="black_friday", month=11, day=28, 
                            year=2025, granularity="block"),
                # Index 1 - should lose
                ExceptionRule(bucket_base_key="campaign_x", month=11, day=28, 
                            year=2025, granularity="block"),
            ],
            fallback=FallbackRule(bucket_base_key="normal", granularity="block"),
        )
        resolver = BucketResolver(profile)
        
        ts = datetime(2025, 11, 28, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts)
        assert result == "black_friday", f"First match should win, got '{result}'"
    
    def test_e4_invalid_time_format_raises(self):
        """E.4: Invalid time format raises ValueError"""
        with pytest.raises(ValueError):
            ScheduleRule(bucket_base_key="bad", days=[1], 
                        start_time="99:99", end_time="25:00", granularity="block")


# ==================== INTEGRATION TESTS ====================

class TestIntegration:
    """Integration tests simulating real-world profiles"""
    
    def test_retail_store_complete_profile(self):
        """Integration: Retail store with holidays, varied hours"""
        profile = BucketProfile(
            profile_id="retail_store",
            timezone="America/New_York",
            exceptions=[
                ExceptionRule(bucket_base_key="holiday_closed", month=11, day=28, 
                            year=2024, granularity="block"),  # Thanksgiving 2024
                ExceptionRule(bucket_base_key="black_friday", month=11, day=29, 
                            year=2024, granularity="block"),
            ],
            schedule=[
                ScheduleRule(bucket_base_key="weekday_retail", days=[1, 2, 3, 4, 5], 
                           start_time="09:00", end_time="21:00", granularity="hourly"),
                ScheduleRule(bucket_base_key="saturday_retail", days=[6], 
                           start_time="10:00", end_time="21:00", granularity="hourly"),
                ScheduleRule(bucket_base_key="sunday_retail", days=[7], 
                           start_time="11:00", end_time="18:00", granularity="hourly"),
            ],
            fallback=FallbackRule(bucket_base_key="store_closed", granularity="block"),
        )
        resolver = BucketResolver(profile)
        
        # Regular Monday 2pm EST = 19:00 UTC
        ts_monday = datetime(2024, 1, 15, 19, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts_monday)
        assert result == "weekday_retail_14", f"Expected weekday_retail_14, got {result}"
        
        # Thanksgiving 2024 (Nov 28 = Thursday)
        ts_thanksgiving = datetime(2024, 11, 28, 19, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts_thanksgiving)
        assert result == "holiday_closed", f"Expected holiday_closed, got {result}"
        
        # Black Friday 8am EST = 13:00 UTC
        ts_bf = datetime(2024, 11, 29, 13, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts_bf)
        assert result == "black_friday", f"Expected black_friday, got {result}"
    
    def test_data_center_24x7_profile(self):
        """Integration: 24/7 data center with maintenance windows"""
        profile = BucketProfile(
            profile_id="data_center",
            timezone="UTC",
            exceptions=[
                ExceptionRule(bucket_base_key="planned_maintenance", month=2, day=15, 
                            year=2024, granularity="block"),
            ],
            schedule=[
                ScheduleRule(bucket_base_key="business_high_traffic", days=[1, 2, 3, 4, 5], 
                           start_time="09:00", end_time="18:00", granularity="hourly"),
                ScheduleRule(bucket_base_key="evening_medium", days=[1, 2, 3, 4, 5], 
                           start_time="18:00", end_time="22:00", granularity="hourly"),
                ScheduleRule(bucket_base_key="weekend_low", days=[6, 7], 
                           start_time="09:00", end_time="18:00", granularity="hourly"),
            ],
            fallback=FallbackRule(bucket_base_key="overnight_minimal", granularity="hourly"),
        )
        resolver = BucketResolver(profile)
        
        # Business hours
        ts_business = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts_business)
        assert result == "business_high_traffic_12"
        
        # Overnight (fallback)
        ts_overnight = datetime(2024, 1, 16, 3, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts_overnight)
        assert result == "overnight_minimal_03"
        
        # Planned maintenance day
        ts_maintenance = datetime(2024, 2, 15, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts_maintenance)
        assert result == "planned_maintenance"
    
    def test_from_dict_factory_method(self):
        """Test BucketProfile.from_dict() factory method"""
        profile_dict = {
            "_id": "test_from_dict",
            "timezone": "America/Chicago",
            "exceptions": [
                {"bucket_base_key": "holiday", "rule": {"month": 12, "day": 25}, "granularity": "block"}
            ],
            "schedule": [
                {"bucket_base_key": "workday", "days": [1, 2, 3, 4, 5], 
                 "time_range": {"start": "09:00", "end": "17:00"}, "granularity": "hourly"}
            ],
            "fallback": {"bucket_base_key": "off_hours", "granularity": "block"}
        }
        
        profile = BucketProfile.from_dict(profile_dict)
        resolver = BucketResolver(profile)
        
        assert profile.profile_id == "test_from_dict"
        assert profile.timezone == "America/Chicago"
        
        # Test it resolves correctly
        # 18:00 UTC = 12:00 CST (business hours)
        ts = datetime(2024, 1, 15, 18, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = resolver.resolve(ts)
        assert result == "workday_12"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
