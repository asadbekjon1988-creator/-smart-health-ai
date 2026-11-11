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


def send_telegram_message(text):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        raise RuntimeError("Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
    from urllib.request import Request, urlopen

    body = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=15) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError("Telegram did not accept the message.")


@app.post("/api/v1/daily-report")
def daily_report():
    if not authorized():
        return jsonify({"error": "Unauthorized."}), 401

    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT h.metric, h.value, h.recorded_at
            FROM health_readings h
            JOIN (
                SELECT metric, MAX(id) AS latest_id
                FROM health_readings
                GROUP BY metric
            ) latest ON latest.latest_id = h.id
            ORDER BY h.metric
            """
        ).fetchall()

    labels = {
        "steps": ("Qadamlar", " qadam"),
        "sleep_duration_minutes": ("Uyqu davomiyligi", " daqiqa"),
        "resting_heart_rate_bpm": ("Tinch holatdagi yurak urishi", " bpm"),
    }
    lines = ["Smart Health AI — kunlik hisobot"]
    if not rows:
        lines.append("Hozircha Health Connect ma’lumotlari kelmagan.")
    else:
        for row in rows:
            label, unit = labels[row["metric"]]
            value = row["value"]
            if row["metric"] == "sleep_duration_minutes":
                hours = int(value) // 60
                minutes = int(value) % 60
                display = f"{hours} soat {minutes} daqiqa"
            else:
                display = f"{value:g}{unit}"
            lines.append(f"{label}: {display}")
        lines.append("Bu ma’lumotga asoslangan umumiy wellness hisoboti, tashxis emas.")

    try:
        send_telegram_message("\n".join(lines))
    except Exception:
        app.logger.exception("Telegram report delivery failed")
        return jsonify({"error": "Telegram delivery failed. Check bot settings."}), 502

    return jsonify({"sent": True, "metrics_count": len(rows)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
