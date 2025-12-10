"""MCP tools for managing bucket profiles.

Per Feature Specification Section 4.5:
- create_bucket_profile(profile_id, timezone, exceptions, schedule, fallback)
- list_bucket_profiles()
- delete_bucket_profile(profile_id)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp.exceptions import ToolError

from bucket_profile_models import (
    BucketProfileConfig,
    ExceptionConfig,
    ExceptionRuleConfig,
    FallbackConfig,
    ScheduleConfig,
    TimeRangeConfig,
)
from db import get_db


def create_bucket_profile(
    profile_id: str,
    timezone: str,
    exceptions: Optional[List[Dict[str, Any]]] = None,
    schedule: Optional[List[Dict[str, Any]]] = None,
    fallback: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a reusable bucket profile for time-context definitions.

    Hierarchy: exceptions (highest priority) → schedule → fallback (lowest priority).
    Within exceptions and schedule, rules are evaluated in order - first match wins.
    Exceptions override schedules, schedules override fallback.

    the Args described below are all and the only fields supported in the profile definition.
    adding extra fields will be silently ignored.

    Args:
        profile_id: Unique string ID for this profile (e.g., "business_hours_v1")
        timezone: IANA timezone string (e.g., "America/New_York")
        exceptions: List of exception rules (holidays). Each entry:
            {
                "bucket_base_key": "holiday_xmas",
                "rule": {"month": 12, "day": 25},
                "granularity": "block"
            }
        schedule: List of schedule rules. Each entry:
            {
                "bucket_base_key": "workday",
                "days": [1,2,3,4,5],
                "time_range": {"start": "09:00", "end": "17:00"},
                "granularity": "hourly",
                "months": null  // optional
            }
        fallback: Fallback configuration:
            {"bucket_base_key": "off_hours", "granularity": "hourly"}
    
    Returns:
        Success message with profile ID.
    
    Raises:
        ToolError: If validation fails or profile already exists.
    """
    if not profile_id or not isinstance(profile_id, str):
        raise ToolError("profile_id must be a non-empty string")
    
    profile_id = profile_id.strip()
    if not profile_id:
        raise ToolError("profile_id cannot be empty")
    
    # Build Pydantic model for validation
    try:
        # Parse exceptions
        parsed_exceptions = []
        for exc in (exceptions or []):
            rule_data = exc.get("rule", {})
            parsed_exceptions.append(ExceptionConfig(
                bucket_base_key=exc.get("bucket_base_key", "exception"),
                rule=ExceptionRuleConfig(
                    month=rule_data.get("month", 1),
                    day=rule_data.get("day", 1),
                    year=rule_data.get("year"),
                ),
                granularity=exc.get("granularity", "block"),
            ))
        
        # Parse schedule
        parsed_schedule = []
        for sched in (schedule or []):
            time_range_data = sched.get("time_range", {})
            parsed_schedule.append(ScheduleConfig(
                bucket_base_key=sched.get("bucket_base_key", "default"),
                days=sched.get("days", []),
                time_range=TimeRangeConfig(
                    start=time_range_data.get("start", "00:00"),
                    end=time_range_data.get("end", "23:59"),
                ),
                granularity=sched.get("granularity", "hourly"),
                months=sched.get("months"),
            ))
        
        # Parse fallback
        fb_data = fallback or {}
        parsed_fallback = FallbackConfig(
            bucket_base_key=fb_data.get("bucket_base_key", "fallback"),
            granularity=fb_data.get("granularity", "hourly"),
        )
        
        # Create full profile config
        profile = BucketProfileConfig(
            _id=profile_id,
            timezone=timezone,
            exceptions=parsed_exceptions,
            schedule=parsed_schedule,
            fallback=parsed_fallback,
        )
        
    except Exception as e:
        raise ToolError(f"Validation error: {e}")
    
    # Check for existing profile
    db = get_db()
    collection = db.get_collection("bucket_profiles")
    
    existing = collection.find_one({"_id": profile_id})
    if existing:
        raise ToolError(f"Bucket profile '{profile_id}' already exists. Use a different ID or delete the existing profile first.")
    
    # Insert into MongoDB
    doc = profile.to_mongodb_doc()
    try:
        collection.insert_one(doc)
    except Exception as e:
        raise ToolError(f"Failed to create bucket profile: {e}")
    
    return f"Bucket profile '{profile_id}' created successfully with timezone '{timezone}'."


def list_bucket_profiles() -> str:
    """List all bucket profiles with usage metadata.
    
    Returns:
        JSON-formatted list of profiles with their configurations and usage counts.
    """
    db = get_db()
    profiles_collection = db.get_collection("bucket_profiles")
    kb_collection = db.get_collection("train_config")
    
    # Fetch all profiles
    profiles = list(profiles_collection.find({}))
    
    # Count usage for each profile
    result = []
    for profile in profiles:
        profile_id = profile.get("_id", "unknown")
        
        # Count KBs referencing this profile
        usage_count = kb_collection.count_documents({"bucket_profile_id": profile_id})
        
        result.append({
            "profile_id": profile_id,
            "timezone": profile.get("timezone", "UTC"),
            "exceptions_count": len(profile.get("exceptions", [])),
            "schedule_count": len(profile.get("schedule", [])),
            "fallback_key": profile.get("fallback", {}).get("bucket_base_key", "fallback"),
            "usage_count": usage_count,
        })
    
    if not result:
        return "No bucket profiles found. Create one using create_bucket_profile."
    
    # Format output
    output_lines = ["Bucket Profiles:\n"]
    for p in result:
        output_lines.append(
            f"  - {p['profile_id']} (TZ: {p['timezone']}, "
            f"exceptions: {p['exceptions_count']}, schedules: {p['schedule_count']}, "
            f"used by: {p['usage_count']} KB(s))"
        )
    
    output_lines.append("\nRaw JSON:")
    output_lines.append(json.dumps(result, indent=2))
    
    return "\n".join(output_lines)


def delete_bucket_profile(profile_id: str) -> str:
    """Delete a bucket profile if not referenced by any KB.
    
    Args:
        profile_id: The ID of the profile to delete.
    
    Returns:
        Success message.
    
    Raises:
        ToolError: If profile doesn't exist or is referenced by KBs.
    """
    if not profile_id or not isinstance(profile_id, str):
        raise ToolError("profile_id must be a non-empty string")
    
    profile_id = profile_id.strip()
    if not profile_id:
        raise ToolError("profile_id cannot be empty")
    
    db = get_db()
    profiles_collection = db.get_collection("bucket_profiles")
    kb_collection = db.get_collection("train_config")
    
    # Check if profile exists
    existing = profiles_collection.find_one({"_id": profile_id})
    if not existing:
        raise ToolError(f"Bucket profile '{profile_id}' not found.")
    
    # Check if profile is referenced by any KB (per referential integrity rules)
    referencing_kbs = list(kb_collection.find(
        {"bucket_profile_id": profile_id},
        {"_id": 1, "name": 1}
    ).limit(5))
    
    if referencing_kbs:
        kb_names = [kb.get("name", str(kb.get("_id"))) for kb in referencing_kbs]
        count = kb_collection.count_documents({"bucket_profile_id": profile_id})
        raise ToolError(
            f"Cannot delete bucket profile '{profile_id}': referenced by {count} KB(s). "
            f"Examples: {', '.join(kb_names[:3])}. "
            "Remove the bucket_profile_id from these KBs first."
        )
    
    # Delete the profile
    try:
        result = profiles_collection.delete_one({"_id": profile_id})
        if result.deleted_count == 0:
            raise ToolError(f"Failed to delete bucket profile '{profile_id}'.")
    except Exception as e:
        raise ToolError(f"Failed to delete bucket profile: {e}")
    
    return f"Bucket profile '{profile_id}' deleted successfully."


def get_bucket_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    """Get a bucket profile by ID.
    
    Args:
        profile_id: The ID of the profile to retrieve.
    
    Returns:
        Profile document or None if not found.
    """
    if not profile_id:
        return None
    
    db = get_db()
    collection = db.get_collection("bucket_profiles")
    return collection.find_one({"_id": profile_id})
