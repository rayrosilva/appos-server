"""Servidor Appos — Flask (compatível com Render, Railway, Fly.io, etc.)."""

from __future__ import annotations

import os
import secrets
import time
import uuid
import threading
from typing import Any

from flask import Flask, request, jsonify

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Database (in-memory — mesma lógica do servidor local)
# ---------------------------------------------------------------------------

class Database:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.users: dict[str, dict[str, Any]] = {}
        self.contacts: dict[str, list[str]] = {}
        self.conversations: dict[str, dict[str, Any]] = {}
        self.messages: dict[str, list[dict[str, Any]]] = {}
        self.client_message_ids: dict[str, dict[str, Any]] = {}
        self.calls: list[dict[str, Any]] = []
        self.tokens: dict[str, str] = {}

    def register(self, name: str, password: str | None = None) -> dict[str, Any]:
        with self.lock:
            uid = f"AP-{secrets.token_hex(4).upper()}"
            token = secrets.token_hex(16)
            self.users[uid] = {
                "id": uid, "name": name, "password": password,
                "created": time.time(), "status": "online",
            }
            self.tokens[token] = uid
            self.contacts[uid] = []
            self_conv_id = f"self-{uid}"
            self.conversations[self_conv_id] = {
                "id": self_conv_id, "name": "Meu espaço",
                "members": [uid], "last_message": "Bem-vindo ao Appos!",
                "last_message_time": time.time(), "is_group": False,
            }
            self.messages[self_conv_id] = [{
                "id": "welcome", "author": "Appos",
                "body": f"Bem-vindo ao Appos! Sua identidade privada é {uid}",
                "mine": False, "timestamp": time.time(), "status": "read",
            }]
            return {"id": uid, "token": token, "name": name}

    def auth(self, token: str) -> str | None:
        return self.tokens.get(token)

    def login(self, uid: str, password: str | None) -> dict[str, Any] | None:
        with self.lock:
            user = self.users.get(uid)
            if not user:
                return None
            if user.get("password") and user["password"] != password:
                return None
            token = secrets.token_hex(16)
            self.tokens[token] = uid
            user["status"] = "online"
            return {"id": uid, "token": token, "name": user["name"]}

    def get_user(self, uid: str) -> dict[str, Any] | None:
        return self.users.get(uid)

    def update_profile(self, uid: str, name: str) -> dict[str, Any] | None:
        with self.lock:
            user = self.users.get(uid)
            if user:
                user["name"] = name
            return user

    def add_contact(self, uid: str, contact_id: str) -> dict[str, Any] | None:
        with self.lock:
            contact = self.users.get(contact_id)
            if not contact or contact_id == uid:
                return None
            if contact_id not in self.contacts.get(uid, []):
                self.contacts.setdefault(uid, []).append(contact_id)
            if uid not in self.contacts.get(contact_id, []):
                self.contacts.setdefault(contact_id, []).append(uid)
            return {"id": contact["id"], "name": contact["name"], "status": contact.get("status", "offline")}

    def remove_contact(self, uid: str, contact_id: str) -> bool:
        with self.lock:
            contacts = self.contacts.get(uid, [])
            if contact_id in contacts:
                contacts.remove(contact_id)
                return True
            return False

    def get_contacts(self, uid: str) -> list[dict[str, Any]]:
        with self.lock:
            result = []
            for cid in self.contacts.get(uid, []):
                user = self.users.get(cid)
                if user:
                    name = user["name"]
                    parts = name.strip().split()
                    initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else "AP"
                    result.append({"id": user["id"], "name": name, "initials": initials, "status": user.get("status", "offline")})
            return result

    def get_conversations(self, uid: str) -> list[dict[str, Any]]:
        with self.lock:
            result = []
            for conv in self.conversations.values():
                if uid in conv["members"]:
                    result.append({
                        "id": conv["id"], "name": conv["name"],
                        "last_message": conv.get("last_message", ""),
                        "last_message_time": conv.get("last_message_time"),
                        "is_group": conv.get("is_group", False), "unread_count": 0,
                    })
            result.sort(key=lambda c: c.get("last_message_time") or 0, reverse=True)
            return result

    def get_or_create_dm(self, uid: str, other_id: str) -> dict[str, Any] | None:
        with self.lock:
            other = self.users.get(other_id)
            if not other:
                return None
            for conv in self.conversations.values():
                if not conv.get("is_group") and set(conv["members"]) == {uid, other_id}:
                    return conv
            conv_id = f"dm-{uuid.uuid4().hex[:8]}"
            conv = {
                "id": conv_id, "name": other["name"], "members": [uid, other_id],
                "last_message": "", "last_message_time": time.time(), "is_group": False,
            }
            self.conversations[conv_id] = conv
            self.messages[conv_id] = []
            return conv

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        return self.messages.get(conversation_id, [])

    def add_message(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(payload.get("conversation_id", "")).strip()
        body = str(payload.get("body", "")).strip()
        client_id = str(payload.get("client_message_id", "")).strip()
        if not conversation_id or not body or not client_id:
            raise ValueError("conversation_id, body e client_message_id são obrigatórios")
        with self.lock:
            if client_id in self.client_message_ids:
                return self.client_message_ids[client_id]
            user = self.users.get(uid, {})
            message = {
                "id": client_id, "author": user.get("name", "Appos"),
                "body": body, "mine": True, "timestamp": time.time(), "status": "sent",
            }
            self.messages.setdefault(conversation_id, []).append(message)
            self.client_message_ids[client_id] = message
            conv = self.conversations.get(conversation_id)
            if conv:
                conv["last_message"] = body
                conv["last_message_time"] = time.time()
            return message

    def add_call(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        contact_id = str(payload.get("contact_id", "")).strip()
        if not contact_id:
            raise ValueError("contact_id é obrigatório")
        contact = self.users.get(contact_id, {})
        item = {
            "id": str(uuid.uuid4()), "contact_id": contact_id,
            "contact_name": contact.get("name", "Contato"),
            "kind": str(payload.get("kind", "audio")),
            "direction": "outgoing", "state": "signaling-only",
            "timestamp": time.time(), "duration_seconds": 0,
        }
        with self.lock:
            self.calls.append(item)
        return item

    def get_calls(self, uid: str) -> list[dict[str, Any]]:
        return list(reversed(self.calls))

    def search_user(self, query: str) -> list[dict[str, Any]]:
        with self.lock:
            results = []
            if query.startswith("AP-"):
                user = self.users.get(query)
                if user:
                    results.append({"id": user["id"], "name": user["name"], "status": user.get("status", "offline")})
            for user in self.users.values():
                if query.lower() in user["name"].lower() and user not in [self.users.get(r["id"]) for r in results]:
                    results.append({"id": user["id"], "name": user["name"], "status": user.get("status", "offline")})
            return results

    def list_users(self) -> list[dict[str, Any]]:
        with self.lock:
            return [{"id": u["id"], "name": u["name"], "status": u.get("status", "offline")} for u in self.users.values()]


DB = Database()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_uid() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return DB.auth(auth[7:])
    return None

def _json_body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {}
    return data

# ---------------------------------------------------------------------------
# CORS — allow all origins
# ---------------------------------------------------------------------------

@app.after_request
def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Cache-Control"] = "no-store"
    return response

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "app": "Appos", "mode": "cloud", "version": "1.0.1"})

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "app": "Appos Server",
        "version": "1.0.1",
        "status": "running",
        "endpoints": ["/health", "/api/register", "/api/login", "/api/users",
                       "/api/contacts", "/api/conversations", "/api/messages", "/api/calls"],
        "users_online": len([u for u in DB.users.values() if u.get("status") == "online"]),
        "total_users": len(DB.users),
    })

# Auth
@app.route("/api/register", methods=["POST"])
def register():
    data = _json_body()
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "nome é obrigatório"}), 400
    result = DB.register(name, data.get("password"))
    return jsonify(result), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = _json_body()
    login_id = str(data.get("id", "")).strip()
    result = DB.login(login_id, data.get("password"))
    if result:
        return jsonify(result)
    return jsonify({"error": "ID ou senha inválidos"}), 401

# Users
@app.route("/api/users/search", methods=["GET"])
def search_users():
    q = request.args.get("q", "")
    if not q:
        return jsonify([])
    return jsonify(DB.search_user(q))

@app.route("/api/users", methods=["GET"])
def list_users():
    return jsonify(DB.list_users())

# Profile
@app.route("/api/profile", methods=["GET", "POST"])
def profile():
    uid = _get_uid()
    if not uid:
        return jsonify({"error": "não autenticado"}), 401
    if request.method == "GET":
        user = DB.get_user(uid)
        if user:
            return jsonify({"id": user["id"], "name": user["name"], "status": user.get("status", "offline")})
        return jsonify({"error": "usuário não encontrado"}), 404
    data = _json_body()
    name = str(data.get("name", "")).strip()
    if name:
        DB.update_profile(uid, name)
    return jsonify({"ok": True})

# Contacts
@app.route("/api/contacts", methods=["GET", "POST"])
def contacts():
    uid = _get_uid()
    if request.method == "GET":
        return jsonify(DB.get_contacts(uid) if uid else [])
    if not uid:
        return jsonify({"error": "não autenticado"}), 401
    data = _json_body()
    contact_id = str(data.get("contact_id", "")).strip()
    if not contact_id:
        return jsonify({"error": "contact_id é obrigatório"}), 400
    result = DB.add_contact(uid, contact_id)
    if result:
        return jsonify(result), 201
    return jsonify({"error": "usuário não encontrado ou é você mesmo"}), 404

@app.route("/api/contacts/<contact_id>", methods=["DELETE"])
def delete_contact(contact_id):
    uid = _get_uid()
    if not uid:
        return jsonify({"error": "não autenticado"}), 401
    if DB.remove_contact(uid, contact_id):
        return jsonify({"ok": True})
    return jsonify({"error": "contato não encontrado"}), 404

# Conversations
@app.route("/api/conversations", methods=["GET"])
def conversations():
    uid = _get_uid()
    if uid:
        return jsonify(DB.get_conversations(uid))
    return jsonify([{"id": "self", "name": "Meu espaço", "last_message": "Conecte-se para ver conversas"}])

@app.route("/api/conversations/dm", methods=["POST"])
def create_dm():
    uid = _get_uid()
    if not uid:
        return jsonify({"error": "não autenticado"}), 401
    data = _json_body()
    other_id = str(data.get("contact_id", "")).strip()
    conv = DB.get_or_create_dm(uid, other_id)
    if conv:
        return jsonify(conv)
    return jsonify({"error": "contato não encontrado"}), 404

# Messages
@app.route("/api/messages/<conversation_id>", methods=["GET"])
def get_messages(conversation_id):
    return jsonify(DB.get_messages(conversation_id))

@app.route("/api/messages", methods=["POST"])
def send_message():
    uid = _get_uid() or "anon"
    data = _json_body()
    try:
        result = DB.add_message(uid, data)
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

# Calls
@app.route("/api/calls", methods=["GET", "POST"])
def calls():
    uid = _get_uid() or "anon"
    if request.method == "GET":
        return jsonify(DB.get_calls(uid))
    data = _json_body()
    try:
        result = DB.add_call(uid, data)
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    app.run(host="0.0.0.0", port=port, debug=False)
