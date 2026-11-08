import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv()
app = Flask(__name__)


@app.get("/")
def home():
    return jsonify({
        "name": "Smart Health AI",
        "status": "starter",
        "message": "Application scaffold is running. No health data source is connected yet.",
        "medical_notice": "Informational wellness support only; not a diagnosis.",
    })


@app.get("/health")
def health_check():
    return jsonify({"ok": True, "timestamp": datetime.now(timezone.utc).isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
