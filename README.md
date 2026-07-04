# Quiz App MCP server

A Python MCP (Model Context Protocol) server built with FastMCP. Exposes tools to:
- **Claude Desktop**, locally, over stdio
- **claude.ai**, remotely, over HTTP (deployed on Render)

Optionally backed by a MySQL database via SQLAlchemy.

## Project layout

```
.
├── server.py           # entry point — branches on RENDER env var (stdio vs HTTP)
├── config.py            # loads .env, exposes shared SQLAlchemy engine
├── tools/
│   ├── __init__.py
│   └── example.py       # tool definitions — register(mcp) adds them to a FastMCP instance
├── .env                  # secrets — never commit
├── .env.example
└── requirements.txt
```

## Setup

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
copy .env.example .env
# fill in .env with real DB credentials (or remove the DB_* lines if unused)
```

## Run locally (stdio)

```powershell
.\venv\Scripts\python.exe server.py
```

Or use the MCP inspector to call tools manually:

```powershell
.\venv\Scripts\python.exe -m mcp dev server.py
```

### Connect to Claude Desktop

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "quizapp": {
      "command": "C:\\path\\to\\project\\venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\project\\server.py"]
    }
  }
}
```

Restart Claude Desktop — tools appear automatically.

## Deploy to Render (HTTP, for claude.ai)

1. Push to GitHub (`.env` is gitignored — never commit it).
2. Create a Render **Web Service** connected to the repo.
3. Set environment variables in the Render dashboard:

   | Variable    | Value          |
   |-------------|----------------|
   | `RENDER`    | `true`         |
   | `DB_HOST`   | your DB host   |
   | `DB_USER`   | your DB user   |
   | `DB_PASSWORD` | your DB password |
   | `DB_NAME`   | your DB name   |

4. Start command: `python server.py`
5. In `server.py`, update `BASE_URL` under the `RENDER` branch to your actual Render URL.
6. In **claude.ai → Settings → Connectors**, add: `https://your-app.onrender.com/mcp`

**No auth is currently configured on the HTTP endpoint** — anyone with the URL can call every
tool, including DB-backed ones. This was an explicit choice to keep setup simple for now; revisit
before exposing anything sensitive (see Security below).

### Note

OAuth was removed from the HTTP endpoint for now — we're not using claude.ai against this
server's DB/tools yet, so it wasn't worth the extra complexity. Add it back later if needed.

### Keep-alive

Render's free tier sleeps after 15 minutes idle, which makes the first request after sleep slow
(30–60s) or time out. Mitigations already in place:
- A background thread in `server.py` pings `/health` every 10 minutes.
- Add an external monitor (e.g. UptimeRobot) on `https://your-app.onrender.com/health` every
  5 minutes — **not** on `/mcp`.

## Adding a new tool

Open `tools/example.py` and add a function inside `register(mcp)`:

```python
@mcp.tool()
def my_new_tool(param1: str, param2: int) -> dict:
    """
    One-sentence description of what this tool does.
    The agent reads this docstring to decide when to call the tool.

    Args:
        param1: What this string parameter means.
        param2: What this integer parameter means.
    """
    result = do_something(param1, param2)
    return {"result": result}
```

No separate registration step — `register(mcp)` is called for both the stdio and HTTP instances.

## Security

- `.env` is gitignored — never commit it.
- Tools never return raw SQL or expose the DB schema.
- All queries use parameterized SQL (`text("... WHERE id = :id")`, not string interpolation).
- Any user-supplied table/column name is checked against an allowlist before use (see
  `count_records` in `tools/example.py`).
- The Render HTTP endpoint has no authentication — treat it as public. Don't add tools that
  expose sensitive data or destructive DB operations until auth is added back.
