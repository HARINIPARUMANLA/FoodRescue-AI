# FoodRescue AI – Save Food, Share Hope

FoodRescue AI is a Flask and SQLite prototype that helps donors list surplus food and recipients discover and request it. It includes rule-based smart matching and RescueBot, a local LLM assistant using Ollama and a simple Retrieval-Augmented Generation (RAG) workflow.

## Features
- Submit and browse food donations
- Submit food requests and manage approval/rejection
- Match donations by category, quantity and location
- RescueBot chatbot powered by Ollama (`llama3.2:3b`)
- Retrieve context from `knowledge_base.txt` and current SQLite donation records

## Requirements
- Python 3.10+
- Ollama installed locally
- Ollama model: `llama3.2:3b`

## Run locally
1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Install/pull the local model in Ollama:
   ```bash
   ollama pull llama3.2:3b
   ```
4. Start Ollama, then start Flask:
   ```bash
   python app.py
   ```
5. Open http://127.0.0.1:5000 in your browser.

The SQLite database `foodrescue.db` is created automatically on first run.

## Important notes
- This is an educational local demonstration, not a production-ready service.
- The matching score is a simple rule-based score, not a trained ML model.
- RescueBot does not browse the live internet; it uses the local knowledge file and database, then calls Ollama on the same computer.
- Before public deployment, add authentication and authorization, CSRF protection, input validation, rate limiting, secure configuration/secrets, and privacy safeguards. Do not commit real user data or your local database.
