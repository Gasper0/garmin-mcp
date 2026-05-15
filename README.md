# 🏃 Garmin MCP Server

A Model Context Protocol (MCP) server that connects Claude to your Garmin Connect data — activities, sleep, recovery, training readiness — and lets Claude push structured workouts directly to your watch.

Works with **Claude Code**, **Claude Desktop**, and **Cowork**.

> **Heads-up:** Garmin Connect doesn't publish an official public API. This MCP relies on the [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect) library, which uses reverse-engineered endpoints. It works well but may break occasionally if Garmin updates their backend.

---

## Available tools

### Reading data
| Tool | Description |
|---|---|
| `get_activities` | Recent activities (running, cycling, swimming...) |
| `get_activity_details` | Full session details (splits, HR zones, cadence) |
| `get_sleep` | Sleep data (score, phases, SpO2, HRV) |
| `get_body_battery` | Body Battery over N days |
| `get_heart_rate` | Resting HR and HRV over N days |
| `get_training_readiness` | Garmin training readiness score |
| `get_weekly_summary` | Full weekly summary (ideal for running coach reviews) |

### Pushing workouts (running)
| Tool | Description |
|---|---|
| `create_workout` | Create a structured workout (intervals, threshold, easy, long run) |
| `schedule_workout` | Schedule an existing workout on a target date |
| `list_workouts` | List scheduled workouts |
| `delete_workout` | Delete a workout from Garmin Connect |
| `schedule_workout_from_calendar` | Generate and schedule a Garmin workout from a Google Calendar event |
| `delete_completed_workouts` | Bulk delete completed workouts after sync |

---

## Why this exists

Pairs especially well with the [running-coach-plugin](https://github.com/Gasper0/running-coach-plugin), which uses this MCP for:
- **Weekly reviews**: automatic fetch of last week's activities + recovery signals
- **Workout building**: design a VMA/threshold/easy run in conversation, pushed directly to the watch
- **Plan execution**: weekly Garmin push as the training plan progresses

The plugin works without this MCP (manual fallback for data input), but the experience is meaningfully smoother with it.

---

## Installation

### Prerequisites

- **Python 3.11+** (check with `python3 --version`, download at https://www.python.org/downloads/)
- **Git** (to clone this repo)
- A **Garmin Connect account** with activities synced

### Step 1 — Clone the repo

```bash
git clone https://github.com/Gasper0/garmin-mcp ~/garmin-mcp
cd ~/garmin-mcp
```

### Step 2 — Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> The virtual environment isolates dependencies from your system Python. Recommended even if you have Python already configured globally.

### Step 3 — Configure your Garmin credentials

```bash
cp .env.example .env
```

Edit `.env` with a text editor:
```
GARMIN_EMAIL=your.email@example.com
GARMIN_PASSWORD=your_password_here
```

> The `.env` file stays on your machine and is gitignored. Your credentials never leave your local environment.

### Step 4 — Test the server starts correctly

```bash
python3 server.py
```

You should see no immediate error and the process should wait for stdin input. Press `Ctrl+C` to stop.

If you see an authentication error, check the troubleshooting section below.

### Step 5 — Connect to your Claude client

Choose your client. You can configure several at once — the configurations are independent.

#### Option A — Claude Code (CLI)

```bash
claude mcp add garmin --scope user -- \
  $HOME/garmin-mcp/venv/bin/python3 \
  $HOME/garmin-mcp/server.py
```

Verify:
```bash
claude mcp list
```

You should see `garmin: ✓ Connected`.

#### Option B — Claude Desktop / Cowork

Edit the config file:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add this block inside `"mcpServers"`:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/full/path/to/garmin-mcp/venv/bin/python3",
      "args": ["/full/path/to/garmin-mcp/server.py"]
    }
  }
}
```

Replace `/full/path/to/garmin-mcp/` with the actual path (e.g. `/Users/yourname/garmin-mcp/`).

Then **fully quit and restart Claude Desktop**. In a new conversation, you should see the 🔌 indicator showing MCP tools are active.

---

## Verification

Open a new conversation in your Claude client and ask:

> "Show me my last 5 Garmin activities"

or

> "Give me a weekly summary of my training data"

If the tools return data, you're set.

---

## Troubleshooting

### `'Garmin' object has no attribute 'garth'` error

This means `garminconnect` was installed in version 0.3.x, which broke compatibility with this MCP. Versions 0.1.0 of this server require `garminconnect` 0.2.x.

**Fix:**

```bash
cd ~/garmin-mcp
source venv/bin/activate
pip install --force-reinstall "garminconnect==0.2.25"
rm -f ~/.garmin_mcp_tokens
```

Then fully restart Claude (Cmd+Q on macOS — closing the window isn't enough) so the MCP server reloads with the new dependency version.

> **Note**: This issue only affects users who installed before v0.1.1. From v0.1.1 onwards, `garminconnect` is pinned to a known-good version in `requirements.txt`.

### Authentication error on first run

- Verify your `GARMIN_EMAIL` and `GARMIN_PASSWORD` in `.env` are correct
- If you have **two-factor authentication (2FA)** enabled on Garmin Connect:
  - Temporarily disable 2FA in your Garmin account settings
  - Run the server once to generate the cached token at `~/.garmin_mcp_tokens`
  - Re-enable 2FA — subsequent runs use the cached token without prompting

### "Tokens expired" or auth fails after several days

The session token at `~/.garmin_mcp_tokens` expired (typically valid ~1 year, but sometimes shorter). Delete it:

```bash
rm ~/.garmin_mcp_tokens
```

The server will re-authenticate from credentials and refresh the token.

### Server not detected in Claude Desktop / Cowork

- Verify the path in `claude_desktop_config.json` is **absolute** (starts with `/`)
- Verify Python is callable: `which python3`
- On Windows, use `python` instead of `python3` if your install uses that command
- Check Claude Desktop logs: open the app, go to Help → "Open Logs Folder"

### Server not detected in Claude Code

```bash
claude mcp list   # is garmin listed and ✓ Connected?
```

If not connected, remove and re-add:
```bash
claude mcp remove garmin
claude mcp add garmin --scope user -- \
  $HOME/garmin-mcp/venv/bin/python3 \
  $HOME/garmin-mcp/server.py
```

### Garmin Connect blocks requests

Garmin sometimes rate-limits or blocks programmatic access:
- Wait 15-30 minutes and retry
- Verify you can log in normally on https://connect.garmin.com
- If Garmin requires a CAPTCHA, the underlying library can't bypass it — log in via the web first, then retry

### See server logs

Launch the server manually to see error output:

```bash
cd ~/garmin-mcp
source venv/bin/activate
python3 server.py
```

---

## Security

- Credentials stored locally only in `.env` (gitignored)
- Session token cached at `~/.garmin_mcp_tokens` (gitignored, local only)
- No data transits through third-party servers — direct connection between your machine and Garmin Connect
- Claude only receives data formatted in response to its tool calls

---

## License

MIT — see [LICENSE](./LICENSE).

This is an **unofficial integration**. Not affiliated with Garmin Ltd. Use at your own risk.
