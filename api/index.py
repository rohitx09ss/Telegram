import os, re, secrets, hashlib, hmac
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, jsonify, session, send_from_directory
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

app = Flask(__name__, static_folder="../public", static_url_path="")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "")
if not app.secret_key:
    raise RuntimeError("Set FLASK_SECRET_KEY in Vercel Environment Variables")

MONGODB_URI = os.environ.get("MONGODB_URI", "")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
if not MONGODB_URI or not ADMIN_PASSWORD:
    raise RuntimeError("Set MONGODB_URI and ADMIN_PASSWORD in Vercel Environment Variables")

client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
db = client[os.environ.get("MONGODB_DB", "numberhub")]
numbers = db.numbers
keys = db.api_keys
users = db.users

def now():
    return datetime.now(timezone.utc).isoformat()

def fail(message, status=400):
    return jsonify({"ok": False, "error": message}), status

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return fail("Admin login required", 401)
        return fn(*args, **kwargs)
    return wrapped

def hash_key(raw):
    return hashlib.sha256(raw.encode()).hexdigest()

def api_key_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        raw = request.headers.get("X-API-Key", "")
        if not raw:
            return fail("Missing X-API-Key header", 401)
        record = keys.find_one({"key_hash": hash_key(raw), "active": True})
        if not record:
            return fail("Invalid or revoked API key", 403)
        keys.update_one({"_id": record["_id"]}, {"$inc": {"requests": 1}, "$set": {"last_used": now()}})
        return fn(*args, **kwargs)
    return wrapped

@app.get("/")
def home():
    return send_from_directory("../public", "index.html")

@app.get("/admin")
def admin_page():
    return send_from_directory("../public", "admin.html")

@app.get("/api/health")
def health():
    try:
        client.admin.command("ping")
        return jsonify({"ok": True, "service": "NumberHub API", "database": "connected"})
    except Exception:
        return fail("Database unavailable", 503)

@app.post("/api/admin/login")
def admin_login():
    data = request.get_json(silent=True) or {}
    if hmac.compare_digest(str(data.get("username", "")), ADMIN_USERNAME) and hmac.compare_digest(str(data.get("password", "")), ADMIN_PASSWORD):
        session.clear()
        session["admin"] = True
        return jsonify({"ok": True})
    return fail("Invalid credentials", 401)

@app.post("/api/admin/logout")
def admin_logout():
    session.clear()
    return jsonify({"ok": True})

@app.get("/api/admin/me")
@admin_required
def admin_me():
    return jsonify({"ok": True})

@app.get("/api/admin/numbers")
@admin_required
def admin_numbers():
    docs = list(numbers.find().sort("created_at", -1))
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return jsonify({"ok": True, "items": docs})

@app.post("/api/admin/numbers")
@admin_required
def add_number():
    data = request.get_json(silent=True) or {}
    phone = str(data.get("phone", "")).strip()
    country = str(data.get("country_code", "")).strip()
    otp = str(data.get("otp", "")).strip()
    if not re.fullmatch(r"\+[1-9]\d{6,14}", phone):
        return fail("Enter a valid international phone number, e.g. +918XXXXXXXXX")
    if not re.fullmatch(r"\+[1-9]\d{0,3}", country):
        return fail("Country code must look like +91")
    if otp and not re.fullmatch(r"\d{4,8}", otp):
        return fail("OTP must contain 4–8 digits")
    if numbers.find_one({"phone": phone}):
        return fail("This number already exists", 409)
    doc = {
        "phone": phone, "country_code": country, "otp": otp,
        "status": data.get("status", "available") if data.get("status") in ("available", "used", "disabled") else "available",
        "created_at": now(), "updated_at": now()
    }
    result = numbers.insert_one(doc)
    return jsonify({"ok": True, "id": str(result.inserted_id)}), 201

@app.patch("/api/admin/numbers/<number_id>")
@admin_required
def update_number(number_id):
    from bson import ObjectId
    data = request.get_json(silent=True) or {}
    updates = {}
    for field in ("phone", "country_code", "otp", "status"):
        if field in data:
            updates[field] = str(data[field]).strip()
    if "status" in updates and updates["status"] not in ("available", "used", "disabled"):
        return fail("Invalid status")
    if "otp" in updates and updates["otp"] and not re.fullmatch(r"\d{4,8}", updates["otp"]):
        return fail("OTP must contain 4–8 digits")
    updates["updated_at"] = now()
    try:
        result = numbers.update_one({"_id": ObjectId(number_id)}, {"$set": updates})
    except Exception:
        return fail("Invalid number ID")
    if not result.matched_count:
        return fail("Number not found", 404)
    return jsonify({"ok": True})

@app.delete("/api/admin/numbers/<number_id>")
@admin_required
def delete_number(number_id):
    from bson import ObjectId
    try:
        result = numbers.delete_one({"_id": ObjectId(number_id)})
    except Exception:
        return fail("Invalid number ID")
    if not result.deleted_count:
        return fail("Number not found", 404)
    return jsonify({"ok": True})

@app.get("/api/admin/keys")
@admin_required
def list_keys():
    docs = list(keys.find({}, {"key_hash": 0}).sort("created_at", -1))
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return jsonify({"ok": True, "items": docs})

@app.post("/api/admin/keys")
@admin_required
def create_key():
    active_count = keys.count_documents({"active": True})
    if active_count >= 10:
        return fail("Maximum of 10 active API keys reached. Revoke or delete one first.", 409)
    label = str((request.get_json(silent=True) or {}).get("label", "API key")).strip()[:60] or "API key"
    raw = "nh_live_" + secrets.token_urlsafe(32)
    keys.insert_one({
        "label": label, "key_hash": hash_key(raw), "active": True,
        "created_at": now(), "last_used": None, "requests": 0
    })
    return jsonify({"ok": True, "api_key": raw, "warning": "Copy this key now. It cannot be shown again."}), 201

@app.patch("/api/admin/keys/<key_id>")
@admin_required
def revoke_key(key_id):
    from bson import ObjectId
    try:
        result = keys.update_one({"_id": ObjectId(key_id)}, {"$set": {"active": False, "revoked_at": now()}})
    except Exception:
        return fail("Invalid key ID")
    if not result.matched_count:
        return fail("Key not found", 404)
    return jsonify({"ok": True})

@app.delete("/api/admin/keys/<key_id>")
@admin_required
def delete_key(key_id):
    from bson import ObjectId
    try:
        result = keys.delete_one({"_id": ObjectId(key_id)})
    except Exception:
        return fail("Invalid key ID")
    if not result.deleted_count:
        return fail("Key not found", 404)
    return jsonify({"ok": True})

@app.get("/api/numbers")
@api_key_required
def public_numbers():
    docs = list(numbers.find({"status": "available"}, {"phone": 1, "country_code": 1, "status": 1}))
    return jsonify({"ok": True, "count": len(docs), "numbers": [
        {"phone": d["phone"], "country_code": d["country_code"], "status": d["status"]} for d in docs
    ]})

@app.get("/api/numbers/<path:phone>/otp")
@api_key_required
def public_otp(phone):
    # Only expose OTP records that the operator is authorized to distribute to this API customer.
    doc = numbers.find_one({"phone": phone, "status": "available"}, {"otp": 1, "phone": 1})
    if not doc:
        return fail("Number not found or unavailable", 404)
    if not doc.get("otp"):
        return jsonify({"ok": True, "phone": doc["phone"], "otp_status": "pending", "otp": None})
    return jsonify({"ok": True, "phone": doc["phone"], "otp_status": "available", "otp": doc["otp"]})

@app.errorhandler(404)
def not_found(_):
    return fail("Not found", 404)

@app.errorhandler(500)
def server_error(_):
    return fail("Internal server error", 500)
