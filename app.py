import hmac
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # Small JSON payloads only.

DB_PATH = os.environ.get("DB_PATH", "data/health.db")
API_TOKEN = os.environ.get("API_TOKEN", "")

ALLOWED_METRICS = {
    "steps": (0, 200000),
    "sleep_duration_minutes": (0, 1440),
    "resting_heart_rate_bpm": (25, 240),
}


def get_db():
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS health_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            source TEXT NOT NULL
        )
        """
    )
    return connection


def authorized():
    supplied = request.headers.get("Authorization", "")
    if not API_TOKEN or not supplied.startswith("Bearer "):
        return False
    return hmac.compare_digest(supplied[7:], API_TOKEN)


def parse_recorded_at(value):
    if not isinstance(value, str):
        raise ValueError("recorded_at must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("recorded_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


@app.get("/")
def home():
    return jsonify({
        "name": "Smart Health AI",
        "status": "backend_ready",
        "message": "Secure data-receiver scaffold is available. Health Connect is not connected yet.",
        "medical_notice": "Informational wellness support only; not a diagnosis.",
    })


@app.get("/health")
def health_check():
    return jsonify({"ok": True, "timestamp": datetime.now(timezone.utc).isoformat()})


@app.post("/api/v1/health-data")
def receive_health_data():
    if not authorized():
        return jsonify({"error": "Unauthorized. Configure API_TOKEN and send a Bearer token."}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Expected a JSON object."}), 400

    source = payload.get("source", "health_connect")
    if source not in ("health_connect", "manual_import"):
        return jsonify({"error": "Unsupported source."}), 400

    try:
        recorded_at = parse_recorded_at(payload.get("recorded_at"))
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    metrics = payload.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        return jsonify({"error": "metrics must be a non-empty object."}), 400

    rows = []
    for metric, value in metrics.items():
        if metric not in ALLOWED_METRICS:
            return jsonify({"error": f"Unsupported metric: {metric}"}), 400
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return jsonify({"error": f"{metric} must be numeric."}), 400
        low, high = ALLOWED_METRICS[metric]
        if not low <= value <= high:
            return jsonify({"error": f"{metric} is outside the accepted range."}), 400
        rows.append((recorded_at, metric, float(value), source))

    with get_db() as connection:
        connection.executemany(
            "INSERT INTO health_readings (recorded_at, metric, value, source) VALUES (?, ?, ?, ?)",
            rows,
        )

    return jsonify({"saved": len(rows), "recorded_at": recorded_at}), 201


@app.get("/api/v1/health-data/latest")
def latest_health_data():
    if not authorized():
        return jsonify({"error": "Unauthorized."}), 401

    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT recorded_at, metric, value, source
            FROM health_readings
            WHERE id IN (
                SELECT MAX(id) FROM health_readings GROUP BY metric
            )
            ORDER BY metric
            """
        ).fetchall()

    return jsonify({"readings": [dict(row) for row in rows]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
