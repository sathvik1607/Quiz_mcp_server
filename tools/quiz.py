import config                    # MUST be first if using DB
import uuid
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from mcp.server.fastmcp import FastMCP


def _next_question_number(after=None):
    with config.engine.connect() as conn:
        if after is None:
            row = conn.execute(text("SELECT MIN(question_number) AS qn FROM questions")).fetchone()
        else:
            row = conn.execute(
                text("SELECT MIN(question_number) AS qn FROM questions WHERE question_number > :after"),
                {"after": after},
            ).fetchone()
    return row.qn


def _current_streak(user_id):
    with config.engine.connect() as conn:
        rows = conn.execute(
            text("SELECT is_correct FROM attempts WHERE user_id = :uid ORDER BY question_number"),
            {"uid": user_id},
        ).fetchall()
    streak = 0
    for r in reversed(rows):
        if not r.is_correct:
            break
        streak += 1
    return streak


def _leaderboard():
    with config.engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT u.full_name, u.unique_id, COALESCE(SUM(a.points_earned), 0) AS total_points
            FROM users u
            LEFT JOIN attempts a ON a.user_id = u.id
            GROUP BY u.id, u.full_name, u.unique_id
            ORDER BY total_points DESC
        """)).fetchall()
    return [
        {"rank": i + 1, "name": r.full_name, "unique_id": r.unique_id, "points": r.total_points}
        for i, r in enumerate(rows)
    ]


def register(mcp: FastMCP) -> None:
    """Register all tools in this file onto the given FastMCP instance."""

    @mcp.tool()
    def register_user(name: str, unique_id: str) -> dict:
        """
        Register a new user for the quiz.

        Args:
            name: The user's full name.
            unique_id: A unique id chosen by the user, at least 4 characters.
        """
        unique_id = unique_id.strip()
        if len(unique_id) < 4:
            return {"error": "unique_id must be at least 4 characters."}

        try:
            with config.engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO users (id, unique_id, full_name) VALUES (:id, :unique_id, :full_name)"),
                    {"id": str(uuid.uuid4()), "unique_id": unique_id, "full_name": name},
                )
        except IntegrityError:
            return {"error": f"unique_id '{unique_id}' is already taken."}

        return {
            "message": f"{name} registered successfully.",
            "unique_id": unique_id,
            "first_question_number": _next_question_number(),
        }

    @mcp.tool()
    def get_question(question_number: int) -> dict:
        """
        Get a quiz question by its number. Call this when the user accepts a
        challenge (e.g. "Accepting Challenge 1" -> question_number=1).

        Args:
            question_number: The number of the question to retrieve.
        """
        with config.engine.connect() as conn:
            row = conn.execute(
                text("SELECT question, points FROM questions WHERE question_number = :qn"),
                {"qn": question_number},
            ).fetchone()

        if row is None:
            return {"error": f"No question found with number {question_number}."}

        return {"question_number": question_number, "question": row.question, "points": row.points}

    @mcp.tool()
    def validate_answer(unique_id: str, question_number: int, answer: str) -> dict:
        """
        Submit an answer for a question and check if it's correct. Each question can
        only be attempted once per user — call this only the first time the user answers
        a given question_number. Returns whether the answer was correct, points earned,
        and the next question number. Does NOT return the leaderboard — call
        generate_leaderboard separately if needed.

        Args:
            unique_id: The user's unique id from registration.
            question_number: The question being answered.
            answer: The submitted answer.
        """
        with config.engine.begin() as conn:
            user = conn.execute(
                text("SELECT id FROM users WHERE unique_id = :uid"),
                {"uid": unique_id},
            ).fetchone()
            if user is None:
                return {"error": f"No user registered with unique_id '{unique_id}'."}

            question = conn.execute(
                text("SELECT answer, points FROM questions WHERE question_number = :qn"),
                {"qn": question_number},
            ).fetchone()
            if question is None:
                return {"error": f"No question found with number {question_number}."}

            already_attempted = conn.execute(
                text(
                    "SELECT 1 FROM attempts WHERE user_id = :user_id AND question_number = :qn"
                ),
                {"user_id": user.id, "qn": question_number},
            ).fetchone()
            if already_attempted:
                return {
                    "error": f"Question {question_number} has already been attempted. Re-attempts are not allowed.",
                    "next_question_number": _next_question_number(after=question_number),
                }

            is_correct = answer.strip().lower() == question.answer.strip().lower()
            points_earned = question.points if is_correct else 0

            conn.execute(
                text(
                    "INSERT INTO attempts (user_id, question_number, submitted_answer, is_correct, points_earned) "
                    "VALUES (:user_id, :qn, :answer, :is_correct, :points_earned)"
                ),
                {"user_id": user.id, "qn": question_number, "answer": answer,
                 "is_correct": is_correct, "points_earned": points_earned},
            )

        return {
            "correct": is_correct,
            "points_earned": points_earned,
            "streak": _current_streak(user.id) if is_correct else 0,
            "next_question_number": _next_question_number(after=question_number),
        }

    @mcp.tool()
    def generate_leaderboard() -> dict:
        """
        Get the current quiz leaderboard, ranked by total points.
        """
        return {"leaderboard": _leaderboard()}
