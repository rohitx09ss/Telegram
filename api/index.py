import os, re, csv, io, hashlib, secrets
from datetime import datetime, timezone
from pathlib import Path
from functools import wraps
from flask import Flask, request, jsonify, session, send_from_directory
from pymongo import MongoClient, ReturnDocument
from bson import ObjectId
from pymongo.errors import PyMongoError

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "CHANGE-ME-BEFORE-DEPLOYMENT")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Lax")

client = None
db = None
try:
    uri = os.environ["MONGODB_URI"]
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[os.environ.get("MONGODB_DB", "numberhub")]
    db.challenge_otps.create_index("expires_at", expireAfterSeconds=0)
    db.challenge_otps.create_index("order_id", unique=True)
except Exception:
    db = None

def now():
    return datetime.now(timezone.utc).isoformat()

def db_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if db is None:
            return jsonify(ok=False, error="Database unavailable"), 503
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return jsonify(ok=False, error="Admin login required"), 401
        return fn(*args, **kwargs)
    return wrapper

def api_key_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if db is None:
            return jsonify(ok=False, error="Database unavailable"), 503
        raw = request.headers.get("X-API-Key", "")
        if not raw:
            return jsonify(ok=False, error="Missing X-API-Key"), 401
        digest = hashlib.sha256(raw.encode()).hexdigest()
        key = db.api_keys.find_one({"hash": digest, "active": True})
        if not key:
            return jsonify(ok=False, error="Invalid or revoked API key"), 401
        request.api_key_hash = digest
        return fn(*args, **kwargs)
    return wrapper

def public_number(doc):
    return {
        "id": str(doc["_id"]),
        "phone": doc["phone"],
        "country_code": doc["country_code"],
        "status": doc["status"]
    }

@app.get("/")
def home():
    return send_from_directory(PUBLIC, "index.html")

@app.get("/admin")
@app.get("/admin/")
def admin_page():
    return send_from_directory(PUBLIC, "admin.html")

@app.get("/<path:name>")
def static_files(name):
    target = (PUBLIC / name).resolve()
    if target.parent != PUBLIC.resolve() or not target.is_file():
        return jsonify(ok=False, error="Not found"), 404
    return send_from_directory(PUBLIC, name)

@app.get("/api/health")
def health():
    if db is None:
        return jsonify(ok=False, database="unavailable", service="NumberHub API"), 503
    try:
        client.admin.command("ping")
        return jsonify(ok=True, database="connected", service="NumberHub API")
    except Exception:
        return jsonify(ok=False, database="unavailable", service="NumberHub API"), 503

@app.post("/api/admin/login")
def admin_login():
    body = request.get_json(silent=True) or {}
    if (secrets.compare_digest(str(body.get("username","")), os.environ.get("ADMIN_USERNAME","admin"))
        and secrets.compare_digest(str(body.get("password","")), os.environ.get("ADMIN_PASSWORD",""))):
        session["admin"] = True
        return jsonify(ok=True)
    return jsonify(ok=False, error="Invalid credentials"), 401

@app.post("/api/admin/logout")
def admin_logout():
    session.clear()
    return jsonify(ok=True)

@app.get("/api/admin/me")
def admin_me():
    return jsonify(ok=bool(session.get("admin")))

@app.get("/api/admin/numbers")
@db_required
@admin_required
def admin_numbers():
    docs = list(db.numbers.find().sort("_id", -1).limit(1000))
    return jsonify(ok=True, numbers=[public_number(x) for x in docs])

@app.get("/api/admin/deleted")
@db_required
@admin_required
def deleted_numbers():
    docs = list(db.deleted_numbers.find().sort("deleted_at", -1).limit(1000))
    rows = [{"id": str(x.get("_id")), "phone": x.get("phone", ""),
             "country_code": x.get("country_code", ""), "status": x.get("status", ""),
             "deleted_at": x.get("deleted_at", ""), "reason": x.get("reason", "admin_delete")}
            for x in docs]
    return jsonify(ok=True, numbers=rows)

@app.post("/api/admin/numbers")
@db_required
@admin_required
def add_number():
    body = request.get_json(silent=True) or {}
    phone = re.sub(r"\s+", "", str(body.get("phone","")))
    cc = str(body.get("country_code","+91")).strip()
    if not re.fullmatch(r"\+[1-9]\d{0,3}", cc) or not re.fullmatch(r"\d{5,15}", phone):
        return jsonify(ok=False, error="Valid country_code and phone digits required"), 400
    if db.numbers.find_one({"phone": phone, "country_code": cc}):
        return jsonify(ok=False, error="Duplicate number"), 409
    doc = {"phone": phone, "country_code": cc, "status":"available", "created_at":now()}
    result = db.numbers.insert_one(doc)
    return jsonify(ok=True, number_id=str(result.inserted_id)), 201

@app.post("/api/admin/numbers/bulk")
@db_required
@admin_required
def bulk_numbers():
    # CSV columns: country_code,phone. OTP/password columns are deliberately ignored.
    file = request.files.get("file")
    if not file:
        return jsonify(ok=False, error="Upload a CSV file using field name 'file'"), 400
    try:
        text = file.stream.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        added, skipped = 0, 0
        for row in reader:
            cc = (row.get("country_code") or row.get("cc") or "+91").strip()
            phone = re.sub(r"\s+", "", (row.get("phone") or row.get("number") or "").strip())
            if not re.fullmatch(r"\+[1-9]\d{0,3}", cc) or not re.fullmatch(r"\d{5,15}", phone):
                skipped += 1; continue
            if db.numbers.find_one({"phone":phone,"country_code":cc}):
                skipped += 1; continue
            db.numbers.insert_one({"phone":phone,"country_code":cc,"status":"available","created_at":now()})
            added += 1
        return jsonify(ok=True, added=added, skipped=skipped)
    except Exception:
        return jsonify(ok=False, error="Could not parse CSV; use UTF-8 CSV with country_code,phone columns"), 400

@app.post("/api/admin/otps/bulk")
@db_required
@admin_required
def bulk_import_challenge_otps():
    """Attach short-lived OTPs to existing reserved orders only."""
    file = request.files.get("file")
    raw_text = request.form.get("text", "")
    try:
        if file:
            raw_text = file.stream.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(raw_text))
        required = {"request_id", "country_code", "phone", "otp"}
        if not reader.fieldnames or not required.issubset({x.strip() for x in reader.fieldnames}):
            return jsonify(ok=False, error="Required columns: request_id,country_code,phone,otp"), 400
        added = skipped = 0
        for row in reader:
            order_id = (row.get("request_id") or "").strip()
            cc = (row.get("country_code") or "").strip()
            phone = re.sub(r"\s+", "", (row.get("phone") or "").strip())
            otp = (row.get("otp") or "").strip()
            if not order_id or not re.fullmatch(r"\+[1-9]\d{0,3}", cc) or not re.fullmatch(r"\d{5,15}", phone) or not re.fullmatch(r"\d{4,8}", otp):
                skipped += 1; continue
            order = db.numbers.find_one({"order_id": order_id, "status": "reserved", "phone": phone, "country_code": cc})
            if not order or db.challenge_otps.find_one({"order_id": order_id}):
                skipped += 1; continue
            db.challenge_otps.insert_one({"order_id": order_id, "phone": phone, "country_code": cc,
                "otp": otp, "api_key_hash": order.get("api_key_hash"), "created_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc) + __import__("datetime").timedelta(minutes=5)})
            added += 1
        return jsonify(ok=True, added=added, skipped=skipped, expires_in_seconds=300)
    except Exception:
        return jsonify(ok=False, error="Invalid CSV. Use UTF-8 CSV with request_id,country_code,phone,otp"), 400

@app.delete("/api/admin/numbers/<number_id>")
@db_required
@admin_required
def delete_number(number_id):
    if not ObjectId.is_valid(number_id):
        return jsonify(ok=False, error="Invalid number ID"), 400
    doc = db.numbers.find_one({"_id": ObjectId(number_id)})
    if not doc:
        return jsonify(ok=False, error="Number not found"), 404
    archive = {"phone": doc.get("phone", ""), "country_code": doc.get("country_code", ""),
               "status": doc.get("status", ""), "deleted_at": now(), "reason": "admin_delete"}
    db.deleted_numbers.insert_one(archive)
    db.numbers.delete_one({"_id": ObjectId(number_id)})
    return jsonify(ok=True)

@app.get("/api/admin/keys")
@db_required
@admin_required
def list_keys():
    docs = list(db.api_keys.find({}, {"hash":0}).sort("_id",-1))
    for d in docs: d["id"] = str(d.pop("_id"))
    return jsonify(ok=True, keys=docs)

@app.post("/api/admin/keys")
@db_required
@admin_required
def create_key():
    if db.api_keys.count_documents({"active":True}) >= 10:
        return jsonify(ok=False,error="Maximum 10 active keys. Revoke one first."), 409
    raw = "nh_" + secrets.token_urlsafe(32)
    db.api_keys.insert_one({"hash":hashlib.sha256(raw.encode()).hexdigest(),
                            "label":(request.get_json(silent=True) or {}).get("label","Customer"),
                            "active":True,"created_at":now()})
    return jsonify(ok=True, api_key=raw, warning="Copy this key now; it is shown only once."), 201

@app.patch("/api/admin/keys/<key_id>")
@db_required
@admin_required
def revoke_key(key_id):
    if not ObjectId.is_valid(key_id): return jsonify(ok=False,error="Invalid key ID"),400
    result = db.api_keys.update_one({"_id":ObjectId(key_id)},{"$set":{"active":False,"revoked_at":now()}})
    return jsonify(ok=result.modified_count == 1)

@app.get("/api/numbers/available")
@db_required
@api_key_required
def available_numbers():
    docs = list(db.numbers.find({"status":"available"}).limit(200))
    return jsonify(ok=True, numbers=[public_number(x) for x in docs])

@app.post("/api/numbers/reserve")
@db_required
@api_key_required
def reserve_number():
    body = request.get_json(silent=True) or {}
    number_id = str(body.get("number_id",""))
    if not ObjectId.is_valid(number_id): return jsonify(ok=False,error="Invalid number_id"),400
    order_id = secrets.token_urlsafe(18)
    doc = db.numbers.find_one_and_update(
        {"_id":ObjectId(number_id),"status":"available"},
        {"$set":{"status":"reserved","reserved_at":now(),"order_id":order_id,"api_key_hash":request.api_key_hash}},
        return_document=ReturnDocument.AFTER)
    if not doc: return jsonify(ok=False,error="Number unavailable"),409
    return jsonify(ok=True,order_id=order_id,number=public_number(doc)),201

@app.get("/api/orders/<order_id>")
@db_required
@api_key_required
def order_status(order_id):
    doc = db.numbers.find_one({"order_id":order_id, "api_key_hash": request.api_key_hash})
    if not doc: return jsonify(ok=False,error="Order not found"),404
    return jsonify(ok=True,order_id=order_id,status=doc["status"],number=public_number(doc))

@app.post("/api/orders/<order_id>/otp/consume")
@db_required
@api_key_required
def consume_order_otp(order_id):
    order = db.numbers.find_one({"order_id": order_id, "status": "reserved", "api_key_hash": request.api_key_hash})
    if not order:
        return jsonify(ok=False, error="Order not found or not owned by this API key"), 404
    otp_doc = db.challenge_otps.find_one_and_delete({"order_id": order_id,
        "api_key_hash": request.api_key_hash, "expires_at": {"$gt": datetime.now(timezone.utc)}})
    if not otp_doc:
        return jsonify(ok=False, error="OTP unavailable, expired, or already consumed"), 404
    db.numbers.update_one({"_id": order["_id"]}, {"$set": {"status": "completed", "completed_at": now()}})
    return jsonify(ok=True, order_id=order_id, otp=otp_doc["otp"], one_time=True)

@app.errorhandler(404)
def not_found(_):
    return jsonify(ok=False,error="Not found"),404
