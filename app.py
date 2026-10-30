
import sqlite3
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, render_template, request, jsonify

# =====================================
# 1. APP CONFIGURATION
# =====================================

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "assistant.db"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL_NAME = "llama3.2:1b"

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates")
)


# =====================================
# 2. DATABASE INITIALIZATION
# =====================================

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

        if "title" not in columns:
            conn.execute("""
                ALTER TABLE notes
                ADD COLUMN title TEXT NOT NULL DEFAULT 'My Note'
            """)

        if "created_at" not in columns:
            conn.execute("""
                ALTER TABLE notes
                ADD COLUMN created_at TEXT NOT NULL DEFAULT ''
            """)


# =====================================
# 3. HOME PAGE
# =====================================

@app.route("/")
def home():
    return render_template("index.html")


# =====================================
# 4. HEALTH CHECK
# =====================================

@app.route("/api/health", methods=["GET"])
def health():

    ollama_status = "connected"

    try:
        with requests.Session() as session:

            session.trust_env = False

            response = session.get(
                "http://127.0.0.1:11434/api/tags",
                timeout=5
            )

            response.raise_for_status()

            models = response.json().get("models", [])

            if not any(
                model.get("name") == MODEL_NAME
                for model in models
            ):
                ollama_status = "model_not_found"

    except requests.exceptions.RequestException:
        ollama_status = "disconnected"

    return jsonify({
        "status": "ok",
        "message": "Personal Assistant backend is running",
        "ollama": ollama_status,
        "model": MODEL_NAME
    })


# =====================================
# 5. AI CHAT WITH OLLAMA
# =====================================

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

    payload = {

        "model": MODEL_NAME,

        "stream": False,

        "messages": [

            {
                "role": "system",

                "content": (
                    "You are a helpful Personal Assistant for a student. "
                    "Understand English and Marathi questions. "
                    "Reply in simple Marathi by default. "
                    "If the user asks for English, reply in English. "
                    "Never reply in Gujarati. "
                    "Give accurate beginner-friendly explanations. "
                    "For programming questions, explain step by step. "
                    "Use simple words and helpful examples."
                )
            },

            {
                "role": "user",
                "content": question
            }

        ],

        "options": {
            "temperature": 0.2
        }
    }

    try:

        print("Sending question to Ollama:", question)

        with requests.Session() as session:

            # Prevent Windows proxy settings
            session.trust_env = False

            response = session.post(
                OLLAMA_URL,
                json=payload,
                timeout=(10, 180)
            )

        response.raise_for_status()

        result = response.json()

        answer = (
            result.get("message") or {}
        ).get("content", "").strip()

        if not answer:

            return jsonify({
                "error": "Ollama returned an empty answer."
            }), 502

        print("Ollama answer received successfully.")

        return jsonify({
            "answer": answer
        })

    except requests.exceptions.ConnectionError as e:

        print("OLLAMA CONNECTION ERROR:", str(e))

        return jsonify({
            "error": "Cannot connect to Ollama. Please check Ollama server.",
            "details": str(e)
        }), 503

    except requests.exceptions.Timeout as e:

        print("OLLAMA TIMEOUT:", str(e))

        return jsonify({
            "error": "AI took too long to respond. Please try again."
        }), 504

    except requests.exceptions.HTTPError as e:

        print("OLLAMA HTTP ERROR:", str(e))

        return jsonify({
            "error": "Ollama API returned an error.",
            "details": str(e)
        }), 502

    except requests.exceptions.RequestException as e:

        print("OLLAMA REQUEST ERROR:", str(e))

        return jsonify({
            "error": "Could not get a response from Ollama.",
            "details": str(e)
        }), 502

    except ValueError as e:

        print("OLLAMA JSON ERROR:", str(e))

        return jsonify({
            "error": "Invalid response received from Ollama."
        }), 502


# =====================================
# 6. SAVE AND SHOW NOTES
# =====================================

@app.route("/api/notes", methods=["GET", "POST"])
def notes():

    if request.method == "GET":

        with sqlite3.connect(DATABASE) as conn:

            conn.row_factory = sqlite3.Row

            rows = conn.execute("""
                SELECT id, title, content, created_at
                FROM notes
                ORDER BY id DESC
            """).fetchall()

        return jsonify([
            dict(row) for row in rows
        ])

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

    created_at = datetime.now().strftime(
        "%d-%m-%Y %I:%M %p"
    )

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


# =====================================
# 7. DELETE NOTES
# =====================================

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


# =====================================
# 8. START FLASK SERVER
# =====================================

if __name__ == "__main__":

    init_db()

    print("\n================================")
    print("PERSONAL ASSISTANT PROJECT")
    print("================================")
    print("Backend: Running")
    print("Website: http://127.0.0.1:5000")
    print("Health: http://127.0.0.1:5000/api/health")
    print("Ollama:", OLLAMA_URL)
    print("AI Model:", MODEL_NAME)
    print("================================\n")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )

