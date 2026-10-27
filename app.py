
import sqlite3
from pathlib import Path

import requests
from flask import Flask, render_template, request, jsonify

# ---------- App Setup ----------
BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "assistant.db"

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates")
)

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "llama3.2:1b"


# ---------- Database ----------
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT 'My Note',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT ''
            )
        """)

        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(notes)"
            ).fetchall()
        }

        # Add title to an older database if needed
        if "title" not in columns:
            conn.execute("""
                ALTER TABLE notes
                ADD COLUMN title TEXT NOT NULL DEFAULT 'My Note'
            """)

        # Add created_at if an older database does not have it
        if "created_at" not in columns:
            conn.execute("""
                ALTER TABLE notes
                ADD COLUMN created_at TEXT NOT NULL DEFAULT ''
            """)


# ---------- Home Page ----------
@app.route("/")
def home():
    return render_template("index.html")


# ---------- Backend Health Check ----------
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "message": "Personal Assistant backend is running"
    })


# ---------- AI Chat with Ollama ----------
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}

    question = data.get("question", "")
    if not isinstance(question, str) or not question.strip():
        question = data.get("message", "")

    if not isinstance(question, str) or not question.strip():
        return jsonify({
            "error": "Please type or speak a question."
        }), 400

    question = question.strip()

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful personal assistant. "
                            "Give clear and useful answers. "
                            "If the user asks in Marathi, answer in Marathi. "
                            "If the user asks in English, answer in English."
                        )
                    },
                    {
                        "role": "user",
                        "content": question
                    }
                ],
                "stream": False
            },
            timeout=180
        )

        response.raise_for_status()
        result = response.json()
        answer = result.get("message", {}).get("content", "").strip()

        if not answer:
            return jsonify({
                "error": "Ollama returned an empty answer."
            }), 502

        return jsonify({"answer": answer})

    except requests.exceptions.ConnectionError:
        return jsonify({
            "error": (
                "Ollama is not responding. "
                "Please start Ollama and try again."
            )
        }), 503

    except requests.exceptions.Timeout:
        return jsonify({
            "error": "AI took too long to respond. Please try again."
        }), 504

    except requests.exceptions.RequestException:
        return jsonify({
            "error": "Could not get a response from Ollama."
        }), 502

    except ValueError:
        return jsonify({
            "error": "Invalid response received from Ollama."
        }), 502


# ---------- Show Notes ----------
@app.route("/api/notes", methods=["GET"])
def get_notes():
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT id, title, content, created_at
            FROM notes
            ORDER BY id DESC
        """).fetchall()

    return jsonify([
        {
            "id": row["id"],
            "title": row["title"],
            "content": row["content"],
            "created_at": row["created_at"]
        }
        for row in rows
    ])


# ---------- Save Note ----------
@app.route("/api/notes", methods=["POST"])
def save_note():
    data = request.get_json(silent=True) or {}

    title = data.get("title", "My Note")
    content = data.get("content", "")

    if not isinstance(title, str) or not isinstance(content, str):
        return jsonify({
            "error": "Title and content must be text."
        }), 400

    title = title.strip() or "My Note"
    content = content.strip()

    if not content:
        return jsonify({
            "error": "Please enter a note."
        }), 400

    from datetime import datetime
    created_at = datetime.now().strftime("%d-%m-%Y %I:%M %p")

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.execute(
            """
            INSERT INTO notes (title, content, created_at)
            VALUES (?, ?, ?)
            """,
            (title, content, created_at)
        )
        note_id = cursor.lastrowid

    return jsonify({
        "id": note_id,
        "title": title,
        "content": content,
        "created_at": created_at,
        "message": "Note saved successfully!"
    }), 201


# ---------- Delete Note ----------
@app.route("/api/notes/<int:note_id>", methods=["DELETE"])
def delete_note(note_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.execute(
            "DELETE FROM notes WHERE id = ?",
            (note_id,)
        )

    if cursor.rowcount == 0:
        return jsonify({
            "error": "Note not found."
        }), 404

    return jsonify({
        "success": True,
        "message": "Note deleted successfully."
    })


# ---------- Start Server ----------
if __name__ == "__main__":
    init_db()
    print("Personal Assistant backend is starting...")
    print("Website: http://127.0.0.1:5000")
    print("Health check: http://127.0.0.1:5000/api/health")

    app.run(host="127.0.0.1", port=5000, debug=True)
