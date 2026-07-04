import builtins, sys
_real_print = builtins.print
def _stderr_print(*args, **kwargs):
    kwargs.setdefault("file", sys.stderr)
    _real_print(*args, **kwargs)
builtins.print = _stderr_print

import os
import config                       # MUST be first import — loads .env before anything else

from mcp.server.fastmcp import FastMCP
from tools import example as example_tools
from tools import leaderboard as leaderboard_tools

_INSTRUCTIONS = (
    "You are connected to the Quiz App server. "
    "Call get_today when the user asks about the current date. "
    "Use count_records to look up row counts in a database table. "
    "Call generate_leaderboard whenever the user asks to see the leaderboard, "
    "standings, or rankings, at any point during the quiz. "
    "IMPORTANT — server cold start: if a tool call times out or returns a connection error "
    "on the first attempt, the server is warming up (takes up to 50 seconds). Tell the user "
    "'The server is starting up — please hold on...' then retry the same tool once after a wait."
    # Add more instructions here as you add more tools.
)

# Module-level mcp — used for stdio (Claude Desktop) and `mcp dev` inspector.
mcp = FastMCP(name="quizapp", json_response=True, instructions=_INSTRUCTIONS)
example_tools.register(mcp)
leaderboard_tools.register(mcp)


if __name__ == "__main__":

    if os.getenv("RENDER"):
        # ── Remote HTTP, no auth (Render deployment) ──────────────────────────
        # NOTE: this endpoint is fully public — anyone with the URL can call
        # every tool, including DB-backed ones. Add auth before this handles
        # anything sensitive.
        import uvicorn

        from starlette.routing import Route
        from starlette.requests import Request
        from starlette.responses import Response, PlainTextResponse

        BASE_URL = "https://your-app.onrender.com"      # <-- CHANGE THIS to your Render URL
        PORT = int(os.getenv("PORT", 8000))

        # Build the HTTP app
        mcp_http = FastMCP(
            name="quizapp",
            json_response=True,
            instructions=_INSTRUCTIONS,
        )
        example_tools.register(mcp_http)
        leaderboard_tools.register(mcp_http)

        # IMPORTANT: inject routes directly into the FastMCP app's router.
        # Do NOT wrap it in an outer Starlette app — that breaks the FastMCP lifespan.
        app = mcp_http.streamable_http_app()

        async def health(request: Request) -> Response:
            return PlainTextResponse("OK")

        app.router.routes.insert(0, Route("/health", endpoint=health, methods=["GET"]))

        # Keep-alive: ping /health every 10 min to prevent Render free tier sleep
        import threading, urllib.request as _req
        def _keepalive():
            import time as _t
            _t.sleep(60)
            while True:
                try:
                    _req.urlopen(f"{BASE_URL}/health", timeout=10)
                except Exception:
                    pass
                _t.sleep(600)
        threading.Thread(target=_keepalive, daemon=True).start()

        print(f"Starting on port {PORT}")
        uvicorn.run(app, host="0.0.0.0", port=PORT)

    else:
        # ── Local stdio (Claude Desktop) ─────────────────────────────────────
        mcp.run(transport="stdio")
