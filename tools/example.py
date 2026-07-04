import config                    # MUST be first if using DB
from datetime import date
from sqlalchemy import text
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register all tools in this file onto the given FastMCP instance."""

    @mcp.tool()
    def get_today() -> dict:
        """
        Return today's date and day of the week.
        Call this when the user asks what today is or needs the current date.
        """
        today = date.today()
        return {
            "date":        today.isoformat(),
            "day_of_week": today.strftime("%A"),
        }

    @mcp.tool()
    def hello(name: str) -> dict:
        """
        Greet a person by name.

        Args:
            name: The person's name.
        """
        return {"message": f"Hello, {name}! Today is {date.today()}."}

    @mcp.tool()
    def count_records(table_name: str) -> dict:
        """
        Count the number of rows in a database table.

        Args:
            table_name: Name of the table to count. Must be an exact match.
        """
        # IMPORTANT: never interpolate user input directly into SQL
        ALLOWED_TABLES = {"orders", "customers", "products"}   # <-- change to your real tables
        if table_name not in ALLOWED_TABLES:
            return {"error": f"Table '{table_name}' is not allowed. Choose from: {ALLOWED_TABLES}"}
        with config.engine.connect() as conn:
            row = conn.execute(text(f"SELECT COUNT(*) AS total FROM `{table_name}`")).fetchone()
        return {"table": table_name, "total": row.total}
