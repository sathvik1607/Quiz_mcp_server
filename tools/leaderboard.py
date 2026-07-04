import logging
from typing import Optional

import config
from sqlalchemy import text
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Adjust these two names if your actual table names differ.
USERS_TABLE = "users"
ANSWERS_TABLE = "attempts"

# One row per registered user, aggregated across their answer submissions.
# completion_time_seconds is a proxy: elapsed time between a user's first
# and last recorded answer (there is no dedicated quiz-start/end column).
_LEADERBOARD_QUERY = f"""
    SELECT
        u.id                                AS id,
        u.unique_id                         AS unique_id,
        u.full_name                         AS full_name,
        u.registered_at                     AS registered_at,
        COUNT(a.id)                         AS questions_attempted,
        COALESCE(SUM(a.is_correct), 0)      AS correct_answers,
        COALESCE(SUM(a.points_earned), 0)   AS score,
        CASE
            WHEN COUNT(a.id) > 0
            THEN TIMESTAMPDIFF(SECOND, MIN(a.answered_at), MAX(a.answered_at))
            ELSE NULL
        END                                  AS completion_time_seconds
    FROM {USERS_TABLE} u
    LEFT JOIN {ANSWERS_TABLE} a ON a.user_id = u.id
    GROUP BY u.id, u.unique_id, u.full_name, u.registered_at
"""


def register(mcp: FastMCP) -> None:
    """Register all tools in this file onto the given FastMCP instance."""

    @mcp.tool()
    def generate_leaderboard(limit: Optional[int] = None) -> dict:
        """
        Generate the quiz leaderboard, ranking all registered users by score.

        Call this whenever the user asks to see the leaderboard, standings,
        or rankings, at any point during the quiz.

        Ranking rules:
          1. Highest total score first.
          2. Ties broken by fastest quiz completion time (elapsed time
             between a user's first and last recorded answer).
          3. Remaining ties broken by earliest registration time.

        Args:
            limit: Optional cap on the number of entries returned (e.g. 10
                   for a "top 10" view). Omit to return the full leaderboard.
        """
        if limit is not None and limit <= 0:
            return {"error": "limit must be a positive integer."}

        try:
            with config.engine.connect() as conn:
                rows = conn.execute(text(_LEADERBOARD_QUERY)).mappings().all()
        except Exception:
            logger.exception("Failed to load leaderboard data")
            return {"error": "Could not load the leaderboard right now. Please try again shortly."}

        if not rows:
            return {"leaderboard": [], "message": "No users have registered yet."}

        if all(row["questions_attempted"] == 0 for row in rows):
            return {"leaderboard": [], "message": "No quiz attempts have been made yet."}

        def sort_key(row):
            completion = row["completion_time_seconds"]
            return (
                -row["score"],
                completion if completion is not None else float("inf"),
                row["registered_at"],
                row["unique_id"],
            )

        ranked = sorted(rows, key=sort_key)
        total_participants = len(ranked)

        if limit is not None:
            ranked = ranked[:limit]

        leaderboard = [
            {
                "rank": index + 1,
                "name": row["full_name"],
                "user_id": row["unique_id"],
                "score": row["score"],
                "correct_answers": row["correct_answers"],
                "questions_attempted": row["questions_attempted"],
                "completion_time_seconds": row["completion_time_seconds"],
            }
            for index, row in enumerate(ranked)
        ]

        logger.info("Generated leaderboard with %d of %d participants", len(leaderboard), total_participants)

        return {
            "leaderboard": leaderboard,
            "total_participants": total_participants,
        }
