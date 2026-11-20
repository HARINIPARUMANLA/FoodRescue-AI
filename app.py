from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import re
import sqlite3
from datetime import datetime
from pathlib import Path
import requests

app = Flask(__name__)
app.secret_key = "foodrescue-ai-local-demo-key"  # For local college demo only

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "foodrescue.db"
KNOWLEDGE_FILE = BASE_DIR / "knowledge_base.txt"


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_table():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_name TEXT NOT NULL,
            food_name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit TEXT NOT NULL,
            prepared_at TEXT NOT NULL,
            deadline TEXT NOT NULL,
            storage TEXT NOT NULL,
            location TEXT NOT NULL,
            contact TEXT NOT NULL,
            description TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS food_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donation_id INTEGER NOT NULL,
            recipient_name TEXT NOT NULL,
            organization TEXT,
            contact TEXT NOT NULL,
            requested_quantity INTEGER NOT NULL,
            purpose TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (donation_id) REFERENCES donations(id)
        )
    """)

    conn.commit()
    conn.close()


# --------------------------------------------------
# RESCUEBOT: RETRIEVAL (RAG)
# --------------------------------------------------

def retrieve_donations(query):
    """Find current, unexpired donations that match the user's words."""
    conn = get_db_connection()

    donations = conn.execute("""
        SELECT food_name, category, quantity, unit,
               location, deadline, storage, description
        FROM donations
        WHERE datetime(deadline) > datetime('now', 'localtime')
        ORDER BY id DESC
        LIMIT 20
    """).fetchall()

    conn.close()

    query_words = {
        word.strip(".,?!:;").lower()
        for word in query.split()
        if len(word.strip(".,?!:;")) > 2
    }

    results = []

    for donation in donations:
        donation_text = (
            str(donation["food_name"]) + " " +
            str(donation["category"]) + " " +
            str(donation["location"]) + " " +
            str(donation["description"] or "")
        ).lower()

        score = sum(1 for word in query_words if word in donation_text)

        if score > 0:
            results.append((score, donation))

    results.sort(key=lambda item: item[0], reverse=True)

    return "\n".join(
        f"Food: {d['food_name']}, Category: {d['category']}, "
        f"Quantity: {d['quantity']} {d['unit']}, "
        f"Location: {d['location']}, Deadline: {d['deadline']}, "
        f"Storage: {d['storage']}, Description: {d['description'] or 'Not provided'}"
        for score, d in results[:5]
    )


def retrieve_knowledge(query):
    """Retrieve the most relevant sections from knowledge_base.txt."""
    if not KNOWLEDGE_FILE.exists():
        return ""

    content = KNOWLEDGE_FILE.read_text(encoding="utf-8")

    sections = [
        section.strip()
        for section in content.split("\n\n")
        if section.strip()
    ]

    stop_words = {
        "the", "is", "a", "an", "and", "or", "to", "of", "in",
        "for", "how", "what", "can", "i", "you", "my", "do",
        "does", "are", "please", "tell", "me", "about"
    }

    query_words = {
        word.strip(".,?!:;").lower()
        for word in query.split()
    } - stop_words

    scored_sections = []

    for section in sections:
        section_words = {
            word.strip(".,?!:;").lower()
            for word in section.split()
        }
        score = len(query_words.intersection(section_words))

        if score > 0:
            scored_sections.append((score, section))

    scored_sections.sort(key=lambda item: item[0], reverse=True)

    return "\n\n".join(section for score, section in scored_sections[:3])


def retrieve_request_status(contact):
    """Find food requests registered with this contact number."""
    conn = get_db_connection()

    requests_data = conn.execute("""
        SELECT
            food_requests.id,
            food_requests.recipient_name,
            food_requests.requested_quantity,
            food_requests.status,
            food_requests.created_at,
            donations.food_name
        FROM food_requests
        JOIN donations
            ON food_requests.donation_id = donations.id
        WHERE food_requests.contact = ?
        ORDER BY food_requests.id DESC
    """, (contact,)).fetchall()

    conn.close()

    if not requests_data:
        return "No food request was found for this contact number. Please check the number and try again."

    results = []

    for item in requests_data:
        results.append(
            f"Request ID: {item['id']}\n"
            f"Food: {item['food_name']}\n"
            f"Quantity requested: {item['requested_quantity']}\n"
            f"Status: {item['status']}\n"
            f"Date: {item['created_at']}"
        )

    return "\n\n".join(results)


def extract_contact_number(message):
    numbers = re.findall(r"\b\d{10}\b", message)
    return numbers[0] if numbers else None


def get_ai_response(message):
    """Send retrieved knowledge and donation records to the local Ollama model."""
    knowledge = retrieve_knowledge(message)
    donation_info = retrieve_donations(message)

    if not knowledge and not donation_info:
        return (
            "I can help with FoodRescue AI, food donations, food requests, "
            "smart matching, food safety and reducing food waste. "
            "Please ask me something related to food rescue."
        )

    prompt = f"""
You are RescueBot, the AI assistant of FoodRescue AI.

Answer the user's question using the information provided below.

KNOWLEDGE BASE:
{knowledge if knowledge else "No relevant knowledge-base section was found."}

AVAILABLE FOOD DONATIONS:
{donation_info if donation_info else "No matching donation records were found."}

RULES:
- Answer in simple and friendly language.
- Focus only on FoodRescue AI and food rescue topics.
- Use actual donation records for food availability questions.
- Mention exact food name, category, quantity, location and deadline when available.
- Never invent donation details or claim food is available without database evidence.
- If no matching donation is found, clearly say so.
- Do not confuse cooked food with raw vegetables or fruits.
- Explain that users can request food from the Find Food page.
- If information is unavailable, say so politely.

USER QUESTION:
{message}

ANSWER:
"""

    url = "http://localhost:11434/api/generate"
    data = {
        "model": "llama3.2:3b",
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(url, json=data, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "Sorry, I could not prepare a reply.")
    except requests.RequestException as error:
        print("Ollama error:", error)
        return (
            "RescueBot cannot connect to Ollama right now. "
            "Please make sure Ollama is running and the llama3.2:3b model is installed."
        )
    except (ValueError, KeyError) as error:
        print("Ollama response error:", error)
        return "Sorry, RescueBot received an unexpected response. Please try again."


# --------------------------------------------------
# WEBSITE PAGES
# --------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chatbot")
def chatbot():
    return render_template("chatbot.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()

    if not message:
        return jsonify({"reply": "Please enter a message."}), 400

    status_keywords = [
        "request status", "my request", "approved",
        "pending", "rejected", "request update"
    ]
    wants_status = any(word in message.lower() for word in status_keywords)

    if wants_status or session.get("awaiting_request_contact"):
        contact = extract_contact_number(message)

        if contact:
            session.pop("awaiting_request_contact", None)
            reply = retrieve_request_status(contact)
        else:
            session["awaiting_request_contact"] = True
            reply = (
                "Please enter your registered 10-digit contact number "
                "so I can check your food request status."
            )

        return jsonify({"reply": reply})

    return jsonify({"reply": get_ai_response(message)})


@app.route("/donate")
def donate():
    return render_template("donate.html")


@app.route("/listings")
def listings():
    conn = get_db_connection()
    donations = conn.execute(
        "SELECT * FROM donations ORDER BY id DESC"
    ).fetchall()
    conn.close()

    return render_template("listings.html", donations=donations)


@app.route("/matching", methods=["GET", "POST"])
def smart_matching():
    conn = get_db_connection()
    matches = []
    searched = False

    if request.method == "POST":
        searched = True

        category = request.form.get("category", "").strip()
        location = request.form.get("location", "").strip()
        quantity_input = request.form.get("quantity", "").strip()

        try:
            quantity = int(quantity_input)
            if quantity <= 0 or not category or not location:
                raise ValueError
        except (ValueError, TypeError):
            conn.close()
            return "Please enter valid matching requirements.", 400

        matches_from_db = conn.execute("""
            SELECT *
            FROM donations
            WHERE LOWER(TRIM(category)) = LOWER(?)
              AND quantity >= ?
              AND LOWER(TRIM(location)) LIKE LOWER(?)
              AND datetime(deadline) > datetime('now', 'localtime')
        """, (
            category,
            quantity,
            "%" + location + "%"
        )).fetchall()

        now = datetime.now()
        scored_matches = []

        for donation in matches_from_db:
            score = 90

            try:
                deadline = datetime.fromisoformat(donation["deadline"])
                hours_left = (deadline - now).total_seconds() / 3600

                if hours_left <= 6:
                    score += 10
                elif hours_left <= 24:
                    score += 8
                elif hours_left <= 48:
                    score += 5
                else:
                    score += 2
            except (ValueError, TypeError):
                pass

            donation_data = dict(donation)
            donation_data["match_score"] = min(score, 100)
            scored_matches.append(donation_data)

        matches = sorted(
            scored_matches,
            key=lambda item: item["match_score"],
            reverse=True
        )

    conn.close()

    return render_template(
        "matching.html",
        matches=matches,
        searched=searched
    )


@app.route("/requests")
def view_requests():
    conn = get_db_connection()

    requests_data = conn.execute("""
        SELECT food_requests.*, donations.food_name
        FROM food_requests
        JOIN donations
            ON food_requests.donation_id = donations.id
        ORDER BY food_requests.id DESC
    """).fetchall()

    conn.close()

    return render_template("requests.html", requests=requests_data)


@app.route("/update-request/<int:request_id>", methods=["POST"])
def update_request(request_id):
    status = request.form.get("status")

    if status not in ["Approved", "Rejected"]:
        return "Invalid request status", 400

    conn = get_db_connection()
    conn.execute("""
        UPDATE food_requests
        SET status = ?
        WHERE id = ?
    """, (status, request_id))
    conn.commit()
    conn.close()

    return redirect(url_for("view_requests"))


@app.route("/request/<int:donation_id>")
def request_food(donation_id):
    conn = get_db_connection()
    donation = conn.execute(
        "SELECT * FROM donations WHERE id = ?",
        (donation_id,)
    ).fetchone()
    conn.close()

    if donation is None:
        return "Food donation not found", 404

    return render_template(
        "request.html",
        donation_id=donation_id,
        donation=donation
    )


@app.route("/submit-request/<int:donation_id>", methods=["POST"])
def submit_request(donation_id):
    conn = get_db_connection()

    donation = conn.execute(
        "SELECT * FROM donations WHERE id = ?",
        (donation_id,)
    ).fetchone()

    if donation is None:
        conn.close()
        return "Food donation not found", 404

    try:
        requested_quantity = int(request.form.get("requested_quantity", ""))

        if requested_quantity <= 0 or requested_quantity > donation["quantity"]:
            conn.close()
            return "Please enter a valid quantity within the available amount.", 400

        conn.execute("""
            INSERT INTO food_requests (
                donation_id, recipient_name, organization,
                contact, requested_quantity, purpose
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            donation_id,
            request.form.get("recipient_name", "").strip(),
            request.form.get("organization", "").strip(),
            request.form.get("contact", "").strip(),
            requested_quantity,
            request.form.get("purpose", "").strip()
        ))

        conn.commit()
        conn.close()

        return """
            <h2>Food Request Submitted Successfully!</h2>
            <p>Your request is pending approval from the donor.</p>
            <a href="/listings">Back to Food Listings</a>
        """

    except ValueError:
        conn.close()
        return "Please enter a valid quantity.", 400


@app.route("/submit-donation", methods=["POST"])
def submit_donation():
    try:
        quantity = int(request.form.get("quantity", ""))
        if quantity <= 0:
            return "Please enter a quantity greater than zero.", 400
    except ValueError:
        return "Please enter a valid quantity.", 400

    conn = get_db_connection()

    conn.execute("""
        INSERT INTO donations (
            donor_name, food_name, category, quantity,
            unit, prepared_at, deadline, storage,
            location, contact, description
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form.get("donor_name", "").strip(),
        request.form.get("food_name", "").strip(),
        request.form.get("category", "").strip(),
        quantity,
        request.form.get("unit", "").strip(),
        request.form.get("prepared_at", "").strip(),
        request.form.get("deadline", "").strip(),
        request.form.get("storage", "").strip(),
        request.form.get("location", "").strip(),
        request.form.get("contact", "").strip(),
        request.form.get("description", "").strip()
    ))

    conn.commit()
    conn.close()

    return """
        <h2>Thank you for donating!</h2>
        <p>Your food donation has been saved successfully.</p>
        <a href="/">Return to Home</a>
    """


# --------------------------------------------------
# START FLASK
# --------------------------------------------------

if __name__ == "__main__":
    create_table()
    app.run(debug=True)
