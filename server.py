#!/usr/bin/env python3
"""
Garmin Connect MCP Server
Exposes Garmin data as tools for Claude Desktop.
"""

import json
import logging
import os
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

import garmin_client as gc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("garmin-mcp")

app = Server("garmin-mcp")


# ── Tool definitions ──────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_activities",
            description=(
                "Fetch recent Garmin activities (runs, cycling, swimming, etc.). "
                "Returns distance, pace, HR, calories, training load and more."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of activities to return (default 10, max 100)",
                        "default": 10,
                    },
                    "activity_type": {
                        "type": "string",
                        "description": "Filter by type: 'running', 'cycling', 'swimming', etc. Leave empty for all.",
                    },
                },
            },
        ),
        types.Tool(
            name="get_activity_details",
            description=(
                "Get detailed stats for a specific activity: splits/laps, HR zones, "
                "cadence, stride length, VO2max estimate. Use get_activities first to get the activity_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {
                        "type": "integer",
                        "description": "Garmin activity ID (from get_activities results)",
                    },
                },
                "required": ["activity_id"],
            },
        ),
        types.Tool(
            name="get_sleep",
            description=(
                "Fetch sleep data for the last N days: total sleep, deep/light/REM phases, "
                "sleep score, SpO2, breathing rate, HRV status."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to fetch (default 7)",
                        "default": 7,
                    },
                },
            },
        ),
        types.Tool(
            name="get_body_battery",
            description=(
                "Fetch Body Battery levels for the last N days: charge/drain per day, "
                "start and end of day values."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to fetch (default 7)",
                        "default": 7,
                    },
                },
            },
        ),
        types.Tool(
            name="get_heart_rate",
            description=(
                "Fetch resting heart rate and HRV (Heart Rate Variability) for the last N days. "
                "Useful for tracking recovery trends."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to fetch (default 7)",
                        "default": 7,
                    },
                },
            },
        ),
        types.Tool(
            name="get_training_readiness",
            description=(
                "Fetch Garmin Training Readiness scores for the last N days. "
                "Score 0-100: indicates how ready the body is for a hard session."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to fetch (default 7)",
                        "default": 7,
                    },
                },
            },
        ),
        types.Tool(
            name="get_weekly_summary",
            description=(
                "Full weekly summary combining all metrics: running sessions, total km/time, "
                "sleep, Body Battery, resting HR, HRV, training readiness. "
                "Ideal for the weekly running coach review."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "week_offset": {
                        "type": "integer",
                        "description": "0 = current week, 1 = last week, 2 = 2 weeks ago, etc.",
                        "default": 0,
                    },
                },
            },
        ),
        types.Tool(
            name="create_workout",
            description=(
                "Create a structured workout on Garmin Connect. "
                "It will sync automatically to the Forerunner 945 via Bluetooth. "
                "Supports warmup, cooldown, intervals, recovery, repeat groups. "
                "Targets can be pace (sec/km), heart rate (bpm), or open. "
                "Example: 10min warmup + 5x1km at 4:45/km with 2min recovery + 10min cooldown."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Workout name displayed on the watch (e.g. 'Intervalles 5x1km')",
                    },
                    "sport": {
                        "type": "string",
                        "description": "Sport type: 'running' (default), 'cycling', 'swimming'",
                        "default": "running",
                    },
                    "steps": {
                        "type": "array",
                        "description": (
                            "List of workout steps. Each step: "
                            "type (warmup/cooldown/interval/recovery/rest/repeat), "
                            "duration_type (time/distance/open), "
                            "duration_value (seconds for time, meters for distance), "
                            "target_type (pace/heart_rate/cadence/open), "
                            "target_value_low, target_value_high. "
                            "Pace values in sec/km (e.g. 4:45/km = 285). "
                            "For repeat steps: repeat_count + repeat_steps (nested list)."
                        ),
                        "items": {"type": "object"},
                    },
                },
                "required": ["name", "steps"],
            },
        ),
        types.Tool(
            name="schedule_workout_from_calendar",
            description=(
                "Create a Garmin workout directly from a Google Calendar event. "
                "Claude reads the calendar event (title, date, description) and calls this tool "
                "to auto-generate and push the structured workout to Garmin Connect. "
                "The workout syncs automatically to the Forerunner 945 via Bluetooth. "
                "Session type is inferred from keywords in the title/description "
                "(intervals, tempo, long run, Hyrox, etc.). "
                "Use custom_steps to override the auto-generated structure with precise targets."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "calendar_event_title": {
                        "type": "string",
                        "description": "Title of the Google Calendar event (e.g. 'Séance Hyrox R2')",
                    },
                    "calendar_event_date": {
                        "type": "string",
                        "description": "Date of the event in YYYY-MM-DD format",
                    },
                    "calendar_event_description": {
                        "type": "string",
                        "description": "Description or notes from the calendar event (optional)",
                        "default": "",
                    },
                    "workout_name": {
                        "type": "string",
                        "description": "Override workout name on Garmin (defaults to event title)",
                    },
                    "sport": {
                        "type": "string",
                        "description": "Sport: 'running' (default), 'cycling', 'swimming'",
                        "default": "running",
                    },
                    "custom_steps": {
                        "type": "array",
                        "description": (
                            "Optional: precise workout steps to override auto-generation. "
                            "Same format as create_workout steps."
                        ),
                        "items": {"type": "object"},
                    },
                },
                "required": ["calendar_event_title", "calendar_event_date"],
            },
        ),
        types.Tool(
            name="list_workouts",
            description="List existing workouts saved on Garmin Connect.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of workouts to return (default 20)",
                        "default": 20,
                    },
                },
            },
        ),
        types.Tool(
            name="schedule_workout",
            description=(
                "Schedule an existing Garmin Connect workout on a specific date. "
                "Once scheduled, the workout appears automatically on the watch as "
                "'Entraînement du jour' — no manual action needed. "
                "Always call this after create_workout or schedule_workout_from_calendar."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workout_id": {
                        "type": "string",
                        "description": "Garmin workout ID returned by create_workout",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date to schedule the workout (YYYY-MM-DD)",
                    },
                },
                "required": ["workout_id", "date"],
            },
        ),
        types.Tool(
            name="delete_completed_workouts",
            description=(
                "Check if a running activity was recorded on a given date and if so, "
                "automatically delete the corresponding structured workouts from Garmin Connect. "
                "Returns full activity stats (distance, pace, HR, cadence, training load, laps) "
                "so Claude can update Google Agenda with the completed session data in the same pass. "
                "Call this when the user says they completed a session."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workout_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of Garmin workout IDs to delete (from Google Agenda extendedProperties)",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date to check for completed activity (YYYY-MM-DD)",
                    },
                },
                "required": ["workout_ids", "date"],
            },
        ),
        types.Tool(
            name="delete_workout",
            description="Delete a workout from Garmin Connect by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workout_id": {
                        "type": "integer",
                        "description": "Garmin workout ID (from create_workout or list_workouts)",
                    },
                },
                "required": ["workout_id"],
            },
        ),
    ]


# ── Tool handlers ─────────────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "get_activities":
            result = gc.get_activities(
                limit=arguments.get("limit", 10),
                activity_type=arguments.get("activity_type"),
            )

        elif name == "get_activity_details":
            result = gc.get_activity_details(
                activity_id=arguments["activity_id"]
            )

        elif name == "get_sleep":
            result = gc.get_sleep(days=arguments.get("days", 7))

        elif name == "get_body_battery":
            result = gc.get_body_battery(days=arguments.get("days", 7))

        elif name == "get_heart_rate":
            result = gc.get_heart_rate(days=arguments.get("days", 7))

        elif name == "get_training_readiness":
            result = gc.get_training_readiness(days=arguments.get("days", 7))

        elif name == "get_weekly_summary":
            result = gc.get_weekly_summary(
                week_offset=arguments.get("week_offset", 0)
            )

        elif name == "schedule_workout_from_calendar":
            result = gc.schedule_workout_from_calendar(
                calendar_event_title=arguments["calendar_event_title"],
                calendar_event_date=arguments["calendar_event_date"],
                calendar_event_description=arguments.get("calendar_event_description", ""),
                workout_name=arguments.get("workout_name"),
                sport=arguments.get("sport", "running"),
                custom_steps=arguments.get("custom_steps"),
            )

        elif name == "create_workout":
            result = gc.create_workout(
                name=arguments["name"],
                steps=arguments["steps"],
                sport=arguments.get("sport", "running"),
            )

        elif name == "list_workouts":
            result = gc.list_workouts(limit=arguments.get("limit", 20))

        elif name == "schedule_workout":
            result = gc.schedule_workout(
                workout_id=arguments["workout_id"],
                date_str=arguments["date"],
            )

        elif name == "delete_completed_workouts":
            result = gc.delete_completed_workouts(
                workout_ids=arguments["workout_ids"],
                date_str=arguments["date"],
            )

        elif name == "delete_workout":
            result = gc.delete_workout(workout_id=arguments["workout_id"])

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    except ValueError as e:
        # Config errors (missing credentials, etc.)
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except Exception as e:
        logger.exception(f"Error calling tool {name}")
        return [types.TextContent(type="text", text=json.dumps({"error": f"Unexpected error: {str(e)}"}))]


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
