"""
Garmin Connect client wrapper.
Handles authentication, token caching, and data fetching.
"""

import os
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from garminconnect import Garmin, GarminConnectAuthenticationError

logger = logging.getLogger(__name__)

TOKEN_CACHE_PATH = Path.home() / ".garmin_mcp_tokens"


def _get_client() -> Garmin:
    """Initialize and return an authenticated Garmin client."""
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    if not email or not password:
        raise ValueError(
            "GARMIN_EMAIL and GARMIN_PASSWORD must be set in your .env file."
        )

    client = Garmin(email=email, password=password)

    # Try loading cached tokens first
    if TOKEN_CACHE_PATH.exists():
        try:
            with open(TOKEN_CACHE_PATH, "r") as f:
                tokens = json.load(f)
            client.login(tokens)
            logger.info("Logged in using cached tokens.")
            return client
        except Exception:
            logger.info("Cached tokens invalid, re-authenticating...")

    # Full login
    try:
        client.login()
        # Save tokens for next time
        with open(TOKEN_CACHE_PATH, "w") as f:
            json.dump(client.garth.dumps(), f)
        logger.info("Authenticated and tokens cached.")
    except GarminConnectAuthenticationError as e:
        raise ValueError(f"Garmin authentication failed: {e}")

    return client


def get_activities(limit: int = 10, activity_type: str = None) -> list[dict]:
    """
    Fetch recent activities.

    Args:
        limit: Number of activities to return (default 10, max 100)
        activity_type: Filter by type e.g. 'running', 'cycling', 'swimming'
    """
    client = _get_client()
    activities = client.get_activities(0, min(limit, 100))

    result = []
    for a in activities:
        atype = a.get("activityType", {}).get("typeKey", "unknown")
        if activity_type and activity_type.lower() not in atype.lower():
            continue

        result.append({
            "id": a.get("activityId"),
            "name": a.get("activityName"),
            "type": atype,
            "date": a.get("startTimeLocal", "")[:10],
            "start_time": a.get("startTimeLocal", ""),
            "duration_minutes": round(a.get("duration", 0) / 60, 1),
            "distance_km": round(a.get("distance", 0) / 1000, 2),
            "avg_pace_min_km": _speed_to_pace(a.get("averageSpeed", 0)),
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "calories": a.get("calories"),
            "elevation_gain_m": a.get("elevationGain"),
            "avg_cadence": a.get("averageRunningCadenceInStepsPerMinute"),
            "training_load": a.get("activityTrainingLoad"),
            "aerobic_effect": a.get("aerobicTrainingEffect"),
            "anaerobic_effect": a.get("anaerobicTrainingEffect"),
        })

    return result


def get_activity_details(activity_id: int) -> dict:
    """
    Fetch detailed stats for a specific activity (splits, laps, HR zones).

    Args:
        activity_id: Garmin activity ID (from get_activities)
    """
    client = _get_client()

    details = client.get_activity_details(activity_id)
    splits = client.get_activity_splits(activity_id)
    hr_zones = client.get_activity_hr_in_timezones(activity_id)

    # Parse laps/splits
    laps = []
    for lap in (splits.get("lapDTOs") or []):
        laps.append({
            "lap": lap.get("lapIndex"),
            "distance_km": round(lap.get("distance", 0) / 1000, 2),
            "duration_min": round(lap.get("duration", 0) / 60, 1),
            "avg_pace": _speed_to_pace(lap.get("averageSpeed", 0)),
            "avg_hr": lap.get("averageHR"),
            "max_hr": lap.get("maxHR"),
        })

    # Parse HR zones
    zones = []
    for z in (hr_zones or []):
        zones.append({
            "zone": z.get("zoneNumber"),
            "seconds_in_zone": z.get("secsInZone"),
            "pct": round(z.get("zonePct", 0), 1),
        })

    metrics = details.get("summaryDTO", {})

    return {
        "activity_id": activity_id,
        "duration_minutes": round(metrics.get("duration", 0) / 60, 1),
        "distance_km": round(metrics.get("distance", 0) / 1000, 2),
        "avg_pace": _speed_to_pace(metrics.get("averageSpeed", 0)),
        "avg_hr": metrics.get("averageHR"),
        "max_hr": metrics.get("maxHR"),
        "calories": metrics.get("calories"),
        "elevation_gain_m": metrics.get("elevationGain"),
        "avg_cadence": metrics.get("averageRunCadence"),
        "avg_stride_length_m": metrics.get("avgStrideLength"),
        "vo2max_estimate": metrics.get("vO2MaxValue"),
        "laps": laps,
        "hr_zones": zones,
    }


def get_sleep(days: int = 7) -> list[dict]:
    """
    Fetch sleep data for the last N days.

    Args:
        days: Number of days to fetch (default 7)
    """
    client = _get_client()
    today = date.today()
    results = []

    for i in range(days):
        day = today - timedelta(days=i)
        day_str = day.isoformat()
        try:
            sleep = client.get_sleep_data(day_str)
            daily = sleep.get("dailySleepDTO", {})
            results.append({
                "date": day_str,
                "score": daily.get("sleepScores", {}).get("overall", {}).get("value"),
                "total_sleep_hours": round(daily.get("sleepTimeSeconds", 0) / 3600, 1),
                "deep_sleep_hours": round(daily.get("deepSleepSeconds", 0) / 3600, 1),
                "light_sleep_hours": round(daily.get("lightSleepSeconds", 0) / 3600, 1),
                "rem_sleep_hours": round(daily.get("remSleepSeconds", 0) / 3600, 1),
                "awake_hours": round(daily.get("awakeSleepSeconds", 0) / 3600, 1),
                "avg_spo2": daily.get("averageSpO2Value"),
                "avg_breathing_rate": daily.get("averageRespirationValue"),
                "hrv_status": daily.get("hrvStatus"),
            })
        except Exception as e:
            logger.warning(f"Could not fetch sleep for {day_str}: {e}")

    return sorted(results, key=lambda x: x["date"])


def get_body_battery(days: int = 7) -> list[dict]:
    """
    Fetch Body Battery data for the last N days.

    Args:
        days: Number of days to fetch (default 7)
    """
    client = _get_client()
    today = date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    end = today.isoformat()

    try:
        data = client.get_body_battery(start, end)
        results = []
        for entry in (data or []):
            charged = entry.get("charged")
            drained = entry.get("drained")
            results.append({
                "date": entry.get("date"),
                "charged": charged,
                "drained": drained,
                "net": (charged or 0) - (drained or 0),
                "end_of_day": entry.get("endOfDayBodyBatteryValue"),
                "start_of_day": entry.get("startOfDayBodyBatteryValue"),
            })
        return sorted(results, key=lambda x: x["date"])
    except Exception as e:
        logger.error(f"Body Battery fetch error: {e}")
        return []


def get_heart_rate(days: int = 7) -> list[dict]:
    """
    Fetch resting heart rate and HRV for the last N days.

    Args:
        days: Number of days to fetch (default 7)
    """
    client = _get_client()
    today = date.today()
    results = []

    for i in range(days):
        day = (today - timedelta(days=i)).isoformat()
        try:
            hr_data = client.get_rhr_day(day)
            hrv_data = client.get_hrv_data(day)

            rhr = None
            if hr_data and "allMetrics" in hr_data:
                metrics = hr_data["allMetrics"].get("metricsMap", {})
                rhr_list = metrics.get("WELLNESS_RESTING_HEART_RATE", [])
                if rhr_list:
                    rhr = rhr_list[0].get("value")

            hrv_weekly = None
            hrv_status = None
            if hrv_data:
                summary = hrv_data.get("hrvSummary", {})
                hrv_weekly = summary.get("weeklyAvg")
                hrv_status = summary.get("status")

            results.append({
                "date": day,
                "resting_hr": rhr,
                "hrv_weekly_avg": hrv_weekly,
                "hrv_status": hrv_status,
            })
        except Exception as e:
            logger.warning(f"HR/HRV fetch error for {day}: {e}")

    return sorted(results, key=lambda x: x["date"])


def get_training_readiness(days: int = 7) -> list[dict]:
    """
    Fetch Training Readiness scores for the last N days.

    Args:
        days: Number of days to fetch (default 7)
    """
    client = _get_client()
    today = date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    end = today.isoformat()

    try:
        data = client.get_training_readiness(start, end)
        results = []
        for entry in (data or []):
            score = entry.get("score") or entry.get("trainingReadinessScore")
            results.append({
                "date": entry.get("calendarDate", entry.get("date", "")),
                "score": score,
                "level": _readiness_level(score),
                "sleep_score": entry.get("sleepScore"),
                "recovery_time_hours": entry.get("recoveryTime"),
                "acute_load": entry.get("acuteLoad"),
            })
        return sorted(results, key=lambda x: x["date"])
    except Exception as e:
        logger.error(f"Training readiness fetch error: {e}")
        return []


def get_weekly_summary(week_offset: int = 0) -> dict:
    """
    Full weekly summary: activities + recovery metrics.
    Designed for the running coach weekly review.

    Args:
        week_offset: 0 = current week, 1 = last week, etc.
    """
    today = date.today()
    # Week starts Monday
    monday = today - timedelta(days=today.weekday()) - timedelta(weeks=week_offset)
    sunday = monday + timedelta(days=6)

    # Fetch all data for the week
    all_activities = get_activities(limit=50)
    week_activities = [
        a for a in all_activities
        if monday.isoformat() <= a["date"] <= sunday.isoformat()
    ]

    running = [a for a in week_activities if "running" in a["type"].lower()]
    sleep = get_sleep(days=7 + week_offset * 7)
    body_battery = get_body_battery(days=7 + week_offset * 7)
    hr = get_heart_rate(days=7 + week_offset * 7)
    readiness = get_training_readiness(days=7 + week_offset * 7)

    # Filter to week range
    week_sleep = [s for s in sleep if monday.isoformat() <= s["date"] <= sunday.isoformat()]
    week_bb = [b for b in body_battery if monday.isoformat() <= b["date"] <= sunday.isoformat()]
    week_hr = [h for h in hr if monday.isoformat() <= h["date"] <= sunday.isoformat()]
    week_readiness = [r for r in readiness if monday.isoformat() <= r["date"] <= sunday.isoformat()]

    # Compute averages
    avg_sleep_score = _avg([s["score"] for s in week_sleep if s["score"]])
    avg_rhr = _avg([h["resting_hr"] for h in week_hr if h["resting_hr"]])
    avg_readiness = _avg([r["score"] for r in week_readiness if r["score"]])
    avg_bb_end = _avg([b["end_of_day"] for b in week_bb if b["end_of_day"]])

    total_run_km = sum(r["distance_km"] for r in running)
    total_run_min = sum(r["duration_minutes"] for r in running)

    return {
        "week": f"{monday.isoformat()} → {sunday.isoformat()}",
        "running_sessions": running,
        "total_running_km": round(total_run_km, 1),
        "total_running_minutes": round(total_run_min, 1),
        "other_activities": [a for a in week_activities if "running" not in a["type"].lower()],
        "recovery": {
            "avg_sleep_score": avg_sleep_score,
            "avg_resting_hr": avg_rhr,
            "avg_body_battery_end_of_day": avg_bb_end,
            "avg_training_readiness": avg_readiness,
            "readiness_level": _readiness_level(avg_readiness),
            "daily_sleep": week_sleep,
            "daily_body_battery": week_bb,
            "daily_hr_hrv": week_hr,
            "daily_readiness": week_readiness,
        },
    }


def create_workout(
    name: str,
    steps: list[dict],
    sport: str = "running",
) -> dict:
    """
    Create a structured workout on Garmin Connect.
    It will sync automatically to the watch via Bluetooth.

    Args:
        name: Workout name (e.g. "Intervalles 5x1km")
        sport: Sport type — "running" (default), "cycling", "swimming"
        steps: List of step dicts. Each step has:
            - type: "warmup" | "cooldown" | "interval" | "recovery" | "rest" | "repeat"
            - duration_type: "time" | "distance" | "open"
            - duration_value: seconds (for time) or meters (for distance)
            - target_type: "pace" | "heart_rate" | "cadence" | "open"
            - target_value_low: lower bound (pace in sec/km, HR in bpm, cadence in spm)
            - target_value_high: upper bound
            - repeat_count: (only for type="repeat") number of repetitions
            - repeat_steps: (only for type="repeat") list of nested steps

    Example steps for 5x1km intervals:
        [
            {"type": "warmup", "duration_type": "time", "duration_value": 600,
             "target_type": "heart_rate", "target_value_low": 100, "target_value_high": 140},
            {"type": "repeat", "repeat_count": 5, "repeat_steps": [
                {"type": "interval", "duration_type": "distance", "duration_value": 1000,
                 "target_type": "pace", "target_value_low": 265, "target_value_high": 280},
                {"type": "recovery", "duration_type": "time", "duration_value": 120,
                 "target_type": "open"}
            ]},
            {"type": "cooldown", "duration_type": "time", "duration_value": 600,
             "target_type": "heart_rate", "target_value_low": 100, "target_value_high": 130},
        ]
    """
    client = _get_client()

    sport_map = {
        "running": "running",
        "cycling": "cycling",
        "swimming": "lap_swimming",
    }
    garmin_sport = sport_map.get(sport.lower(), "running")

    workout_steps = []
    step_order = [0]  # mutable counter for recursive step building

    def build_step(s: dict) -> dict:
        step_order[0] += 1
        order = step_order[0]

        # ── Repeat groups: separate DTO with only the fields Garmin expects ──
        if s.get("type") == "repeat":
            return {
                "type": "RepeatGroupDTO",
                "stepOrder": order,
                "numberOfIterations": s.get("repeat_count", 1),
                "smartRepeat": False,
                "workoutSteps": [build_step(rs) for rs in s.get("repeat_steps", [])],
            }

        # ── Executable steps (warmup, cooldown, interval, recovery, rest) ──
        step_type_map = {
            "warmup": "warmup",
            "cooldown": "cooldown",
            "interval": "interval",
            "recovery": "recovery",
            "rest": "rest",
        }
        garmin_step_type = step_type_map.get(s["type"], "interval")

        # Duration
        duration_type = s.get("duration_type", "open")
        duration_value = s.get("duration_value", 0)

        if duration_type == "time":
            end_condition = "time"
            end_condition_value = duration_value  # seconds
        elif duration_type == "distance":
            end_condition = "distance"
            end_condition_value = duration_value  # meters
        else:
            end_condition = "lap.button"
            end_condition_value = None

        # Target
        target_type = s.get("target_type", "open")
        target_low = s.get("target_value_low")
        target_high = s.get("target_value_high")

        if target_type == "pace":
            # Garmin expects speed in m/s for pace targets
            # pace is in sec/km → speed = 1000 / pace_sec
            t_low = round(1000 / target_high, 4) if target_high else None  # inverted: slower pace = lower speed
            t_high = round(1000 / target_low, 4) if target_low else None
            garmin_target = "pace.zone"
        elif target_type == "heart_rate":
            t_low = target_low
            t_high = target_high
            garmin_target = "heart.rate.zone"
        elif target_type == "cadence":
            t_low = target_low
            t_high = target_high
            garmin_target = "cadence"
        else:
            t_low = None
            t_high = None
            garmin_target = "no.target"

        return {
            "type": "ExecutableStepDTO",
            "stepId": None,
            "stepOrder": order,
            "stepType": {"stepTypeId": _step_type_id(garmin_step_type), "stepTypeKey": garmin_step_type},
            "endCondition": {"conditionTypeKey": end_condition, "conditionTypeId": _end_condition_id(end_condition)},
            "endConditionValue": end_condition_value,
            "targetType": {"workoutTargetTypeId": _target_type_id(garmin_target), "workoutTargetTypeKey": garmin_target},
            "targetValueOne": t_low,
            "targetValueTwo": t_high,
        }

    for s in steps:
        workout_steps.append(build_step(s))

    payload = {
        "sportType": {"sportTypeId": _sport_type_id(garmin_sport), "sportTypeKey": garmin_sport},
        "workoutName": name,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": {"sportTypeId": _sport_type_id(garmin_sport), "sportTypeKey": garmin_sport},
                "workoutSteps": workout_steps,
            }
        ],
    }

    try:
        result = client.garth.connectapi(
            "/workout-service/workout",
            method="POST",
            json=payload,
        )
        workout_id = result.get("workoutId")
        return {
            "success": True,
            "workout_id": workout_id,
            "workout_name": name,
            "message": f"Workout '{name}' created successfully on Garmin Connect. It will sync to your Forerunner 945 on next Bluetooth sync.",
            "steps_count": len(steps),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def schedule_workout_from_calendar(
    calendar_event_title: str,
    calendar_event_date: str,
    calendar_event_description: str = "",
    workout_name: str = None,
    sport: str = "running",
    custom_steps: list[dict] = None,
) -> dict:
    """
    Create a Garmin workout from a Google Calendar event.
    Claude reads the calendar event and calls this tool with the event details.
    The workout is auto-generated from the event title/description, then pushed to Garmin Connect.

    Args:
        calendar_event_title: Title of the Google Calendar event
        calendar_event_date: Date of the event (YYYY-MM-DD)
        calendar_event_description: Description/notes from the calendar event (optional)
        workout_name: Override the workout name (defaults to calendar event title)
        sport: Sport type — "running" (default), "cycling", "swimming"
        custom_steps: If provided, use these steps directly instead of auto-generating.
                      Same format as create_workout steps.
    """
    name = workout_name or calendar_event_title

    # If custom steps are provided, use them directly
    if custom_steps:
        steps = custom_steps
    else:
        # Auto-generate a generic structured session based on title/description keywords
        title_lower = (calendar_event_title + " " + calendar_event_description).lower()

        # Detect session type from keywords
        if any(k in title_lower for k in ["interval", "fraction", "seuil", "vma", "vo2"]):
            # Interval session
            steps = [
                {"type": "warmup", "duration_type": "time", "duration_value": 600,
                 "target_type": "heart_rate", "target_value_low": 100, "target_value_high": 140},
                {"type": "repeat", "repeat_count": 5, "repeat_steps": [
                    {"type": "interval", "duration_type": "distance", "duration_value": 1000,
                     "target_type": "open"},
                    {"type": "recovery", "duration_type": "time", "duration_value": 120,
                     "target_type": "open"},
                ]},
                {"type": "cooldown", "duration_type": "time", "duration_value": 600,
                 "target_type": "heart_rate", "target_value_low": 100, "target_value_high": 130},
            ]
        elif any(k in title_lower for k in ["tempo", "threshold", "allure", "seuil"]):
            # Tempo run
            steps = [
                {"type": "warmup", "duration_type": "time", "duration_value": 600,
                 "target_type": "heart_rate", "target_value_low": 100, "target_value_high": 140},
                {"type": "interval", "duration_type": "time", "duration_value": 1200,
                 "target_type": "heart_rate", "target_value_low": 155, "target_value_high": 170},
                {"type": "cooldown", "duration_type": "time", "duration_value": 600,
                 "target_type": "heart_rate", "target_value_low": 100, "target_value_high": 130},
            ]
        elif any(k in title_lower for k in ["long", "sortie longue", "endurance", "lsl"]):
            # Long run
            steps = [
                {"type": "warmup", "duration_type": "time", "duration_value": 600,
                 "target_type": "heart_rate", "target_value_low": 100, "target_value_high": 135},
                {"type": "interval", "duration_type": "time", "duration_value": 3600,
                 "target_type": "heart_rate", "target_value_low": 130, "target_value_high": 150},
                {"type": "cooldown", "duration_type": "time", "duration_value": 600,
                 "target_type": "heart_rate", "target_value_low": 100, "target_value_high": 130},
            ]
        elif any(k in title_lower for k in ["hyrox", "cross", "circuit"]):
            # Hyrox / cross-training — use open targets
            steps = [
                {"type": "warmup", "duration_type": "time", "duration_value": 600,
                 "target_type": "open"},
                {"type": "interval", "duration_type": "open", "duration_value": 0,
                 "target_type": "heart_rate", "target_value_low": 140, "target_value_high": 180},
                {"type": "cooldown", "duration_type": "time", "duration_value": 600,
                 "target_type": "open"},
            ]
        else:
            # Default: easy run with open duration
            steps = [
                {"type": "warmup", "duration_type": "time", "duration_value": 600,
                 "target_type": "heart_rate", "target_value_low": 100, "target_value_high": 135},
                {"type": "interval", "duration_type": "open", "duration_value": 0,
                 "target_type": "heart_rate", "target_value_low": 130, "target_value_high": 150},
                {"type": "cooldown", "duration_type": "time", "duration_value": 600,
                 "target_type": "heart_rate", "target_value_low": 100, "target_value_high": 130},
            ]

    result = create_workout(name=name, steps=steps, sport=sport)
    result["calendar_event"] = calendar_event_title
    result["scheduled_date"] = calendar_event_date
    return result


def delete_workout(workout_id: int) -> dict:
    """Delete a workout from Garmin Connect by its ID."""
    client = _get_client()
    try:
        client.garth.connectapi(
            f"/workout-service/workout/{workout_id}",
            method="DELETE",
        )
        return {"success": True, "message": f"Workout {workout_id} deleted."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_workouts(limit: int = 20) -> list[dict]:
    """List existing workouts saved on Garmin Connect."""
    client = _get_client()
    try:
        workouts = client.garth.connectapi(
            "/workout-service/workouts",
            params={"start": 0, "limit": limit},
        )
        return [
            {
                "workout_id": w.get("workoutId"),
                "name": w.get("workoutName"),
                "sport": w.get("sportType", {}).get("sportTypeKey"),
                "created": w.get("createdDate", "")[:10],
                "updated": w.get("updatedDate", "")[:10],
            }
            for w in (workouts or [])
        ]
    except Exception as e:
        return [{"error": str(e)}]
def schedule_workout(workout_id: str, date_str: str) -> dict:
    """
    Schedule a Garmin Connect workout on a specific date.
    The workout appears automatically on the watch as "Entraînement du jour".
    """
    client = _get_client()
    try:
        response = client.garth.post(
            "connectapi",
            f"/workout-service/schedule/{workout_id}",
            json={"date": date_str},
        )
        # Garmin returns 204 No Content on success — handle both empty and JSON responses
        if hasattr(response, 'get'):
            schedule_id = response.get("id") or response.get("scheduleId") or str(response)
        else:
            schedule_id = str(response) if response else "scheduled"
        return {
            "success": True,
            "workout_id": workout_id,
            "schedule_id": schedule_id,
            "date": date_str,
            "message": f"Workout {workout_id} scheduled on {date_str}. It will appear on the watch as 'Entraînement du jour'.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_completed_workouts(workout_ids: list[str], date_str: str) -> dict:
    """
    Delete structured workouts from Garmin Connect if the session was completed.
    Checks for a running activity on date_str before deleting.
    Returns full activity stats so Claude can update Google Agenda in the same pass.

    Args:
        workout_ids: list of Garmin workout IDs to delete (from Google Agenda extendedProperties)
        date_str: date to check for completed activity e.g. "2026-03-15"

    Returns:
        dict with keys: activity_found, activity_stats, deleted, skipped, errors
        activity_stats contains all data needed to update Google Agenda description.
    """
    client = _get_client()

    # Find the running activity on this date
    all_activities = client.get_activities(0, 20)
    matching = [
        a for a in all_activities
        if a.get("startTimeLocal", "")[:10] == date_str and
        "run" in a.get("activityType", {}).get("typeKey", "").lower()
    ]

    if not matching:
        logger.info(f"No running activity found on {date_str} — skipping cleanup.")
        return {
            "activity_found": False,
            "activity_stats": None,
            "deleted": [],
            "skipped": workout_ids,
            "errors": [],
        }

    # Get stats from the most recent matching activity
    raw = matching[0]
    activity_id = raw.get("activityId")
    start_time  = raw.get("startTimeLocal", "")  # e.g. "2026-03-15 09:29:38"

    # Compute end time from start + duration
    end_time = ""
    try:
        from datetime import datetime, timedelta
        dt_start  = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        dt_end    = dt_start + timedelta(seconds=raw.get("duration", 0))
        end_time  = dt_end.strftime("%Y-%m-%dT%H:%M:%S")
        start_time = dt_start.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        pass

    activity_stats = {
        "name":            raw.get("activityName", ""),
        "date":            date_str,
        "start_time":      start_time,   # ISO format for Google Agenda update
        "end_time":        end_time,     # ISO format for Google Agenda update
        "distance_km":     round(raw.get("distance", 0) / 1000, 2),
        "duration_min":    round(raw.get("duration", 0) / 60, 1),
        "avg_pace":        _speed_to_pace(raw.get("averageSpeed", 0)),
        "avg_hr":          raw.get("averageHR"),
        "max_hr":          raw.get("maxHR"),
        "calories":        raw.get("calories"),
        "avg_cadence":     round(raw.get("averageRunningCadenceInStepsPerMinute", 0) or 0),
        "training_load":   round(raw.get("activityTrainingLoad", 0) or 0),
        "aerobic_effect":  round(raw.get("aerobicTrainingEffect", 0) or 0, 1),
    }

    # Get lap details if available
    try:
        details = client.get_activity_details(activity_id)
        activity_stats["laps"] = details.get("laps", [])
    except Exception:
        activity_stats["laps"] = []

    # Delete the workouts
    deleted, skipped, errors = [], [], []
    for wid in workout_ids:
        try:
            client.garth.connectapi(
                f"/workout-service/workout/{wid}",
                method="DELETE",
            )
            logger.info(f"Deleted workout {wid}")
            deleted.append(wid)
        except Exception as e:
            logger.error(f"Failed to delete workout {wid}: {e}")
            errors.append({"workout_id": wid, "error": str(e)})

    return {
        "activity_found": True,
        "activity_stats": activity_stats,
        "deleted": deleted,
        "skipped": skipped,
        "errors": errors,
        "message": f"{len(deleted)} workout(s) deleted after completed session on {date_str}.",
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _speed_to_pace(speed_ms: float) -> str | None:
    """Convert speed in m/s to pace string mm:ss/km."""
    if not speed_ms or speed_ms <= 0:
        return None
    pace_sec = 1000 / speed_ms
    mins = int(pace_sec // 60)
    secs = int(pace_sec % 60)
    return f"{mins}:{secs:02d}/km"


def _readiness_level(score) -> str:
    if score is None:
        return "unknown"
    if score >= 75:
        return "🟢 High"
    elif score >= 50:
        return "🟡 Moderate"
    elif score >= 25:
        return "🟠 Low"
    else:
        return "🔴 Very low"


def _avg(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 1) if clean else None


def _sport_type_id(key: str) -> int:
    return {"running": 1, "cycling": 2, "lap_swimming": 4}.get(key, 1)


def _step_type_id(key: str) -> int:
    return {"warmup": 1, "cooldown": 2, "interval": 3, "recovery": 4, "rest": 5, "repeat": 6, "other": 7}.get(key, 3)


def _end_condition_id(key: str) -> int:
    return {"lap.button": 1, "time": 2, "distance": 3, "calories": 4, "heart.rate": 5}.get(key, 1)


def _target_type_id(key: str) -> int:
    return {
        "no.target": 1, "power.zone": 2, "cadence": 3,
        "heart.rate.zone": 4, "pace.zone": 6,
    }.get(key, 1)
