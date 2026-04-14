#!/usr/bin/env python3
"""
The Life Shield — Flask API
Full backend with in-memory storage for all 4 modules:
  1. Billing / Subscriptions
  2. Credit Reports
  3. Disputes
  4. Tim Shaw AI Chat
"""
import os
import json
import secrets
import uuid
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ─── CORS (belt + suspenders) ─────────────────────────────────────────────────

@app.after_request
def after_request(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Max-Age"] = "3600"
    return response


# ─── IN-MEMORY STORES ─────────────────────────────────────────────────────────

USERS = {}           # email -> user dict
TOKENS = {}          # token -> {user_id, email}

SUBSCRIPTIONS = {}   # user_id -> subscription dict
PAYMENT_METHODS = {} # user_id -> list[payment_method]
BILLING_HISTORY = {} # user_id -> list[payment]

CREDIT_REPORTS = {}  # user_id -> {equifax, experian, transunion, history}

DISPUTES = {}        # user_id -> list[dispute]

CHAT_HISTORY = {}    # user_id -> list[message]


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"

def get_auth_user():
    """Extract user from Bearer token. Returns (user_dict, error_response)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, (jsonify({"error": "Unauthorized", "code": "UNAUTHORIZED"}), 401)
    token = auth[7:]
    if token not in TOKENS:
        return None, (jsonify({"error": "Invalid token", "code": "INVALID_TOKEN"}), 401)
    token_data = TOKENS[token]
    user = USERS.get(token_data["email"])
    if not user:
        return None, (jsonify({"error": "User not found"}), 404)
    return user, None

def seed_credit_reports(user_id: str):
    """Seed demo credit data for a new user."""
    CREDIT_REPORTS[user_id] = {
        "equifax":   {"bureau": "equifax",   "score": 642, "pulled_at": now_iso(), "grade": "Fair"},
        "experian":  {"bureau": "experian",  "score": 658, "pulled_at": now_iso(), "grade": "Fair"},
        "transunion":{"bureau": "transunion","score": 651, "pulled_at": now_iso(), "grade": "Fair"},
        "tradelines": [
            {"id": "tl_001", "type": "credit_card", "creditor": "Capital One",   "amount": 1200, "status": "delinquent",  "date": "2023-04-01", "bureau": "equifax"},
            {"id": "tl_002", "type": "auto_loan",   "creditor": "Chase Auto",    "amount": 8500, "status": "current",     "date": "2024-01-15", "bureau": "experian"},
            {"id": "tl_003", "type": "collection",  "creditor": "Portfolio Rec", "amount": 340,  "status": "collection",  "date": "2022-11-05", "bureau": "transunion"},
        ],
        "inquiries": [
            {"id": "inq_001", "creditor": "Discover",   "date": "2024-09-10", "bureau": "equifax"},
            {"id": "inq_002", "creditor": "Wells Fargo", "date": "2024-08-22", "bureau": "experian"},
        ],
        "negative_items": [
            {"id": "neg_001", "type": "late_payment", "creditor": "Capital One",   "amount": 1200, "status": "120 days late", "date": "2023-04-01", "bureau": "equifax"},
            {"id": "neg_002", "type": "collection",   "creditor": "Portfolio Rec", "amount": 340,  "status": "collection",    "date": "2022-11-05", "bureau": "transunion"},
        ],
        "score_history": [
            {"date": "2025-01-01", "equifax": 618, "experian": 622, "transunion": 619, "average": 620},
            {"date": "2025-02-01", "equifax": 625, "experian": 631, "transunion": 628, "average": 628},
            {"date": "2025-03-01", "equifax": 635, "experian": 645, "transunion": 638, "average": 639},
            {"date": "2025-04-01", "equifax": 642, "experian": 658, "transunion": 651, "average": 650},
        ],
    }

def seed_subscription(user_id: str):
    """Seed a free subscription for a new user."""
    SUBSCRIPTIONS[user_id] = {
        "id": new_id("sub_"),
        "user_id": user_id,
        "plan_id": "plan_free",
        "plan_name": "Free",
        "price_monthly": 0,
        "status": "active",
        "started_at": now_iso(),
        "next_billing_at": None,
        "features": ["basic_monitoring", "score_check"],
    }
    BILLING_HISTORY[user_id] = []
    PAYMENT_METHODS[user_id] = []

def tim_shaw_respond(message: str, history: list) -> str:
    """Simple rule-based Tim Shaw AI response. Replace with real AI later."""
    msg_lower = message.lower()

    greetings = ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"]
    if any(g in msg_lower for g in greetings):
        return (
            "Hello! I'm Tim Shaw, your personal credit advisor. I'm here to help you "
            "understand your credit, dispute inaccuracies, and build a stronger financial future. "
            "What can I help you with today?"
        )

    if any(w in msg_lower for w in ["score", "credit score"]):
        return (
            "Your credit score is determined by 5 key factors: Payment History (35%), "
            "Amounts Owed (30%), Length of Credit History (15%), New Credit (10%), and "
            "Credit Mix (10%). Based on your current reports, I see room for improvement. "
            "Would you like me to walk you through a personalized action plan?"
        )

    if any(w in msg_lower for w in ["dispute", "inaccurate", "wrong", "error", "incorrect"]):
        return (
            "Disputing inaccurate information is one of the most powerful tools in credit repair. "
            "Under the FCRA, you have the right to dispute any item that is inaccurate, incomplete, "
            "or unverifiable. I can help you identify dispute candidates on your report and draft "
            "professional dispute letters. Would you like to start a dispute?"
        )

    if any(w in msg_lower for w in ["collection", "collections", "debt"]):
        return (
            "Collections can significantly impact your credit score. There are several strategies "
            "we can explore: debt validation, pay-for-delete negotiations, or disputing inaccuracies. "
            "The right approach depends on the age of the debt and whether it's accurately reported. "
            "Let me review your specific collections and recommend the best path forward."
        )

    if any(w in msg_lower for w in ["improve", "better", "raise", "increase", "boost"]):
        return (
            "Great news — improving your credit is absolutely achievable! Here's my recommended "
            "roadmap: (1) Dispute all inaccurate items first — fastest wins. (2) Reduce credit "
            "card utilization below 30%. (3) Ensure all current accounts stay current. (4) Avoid "
            "new hard inquiries for 6 months. Most clients see meaningful improvement within 60-90 days. "
            "Want me to build your personalized plan?"
        )

    if any(w in msg_lower for w in ["billing", "plan", "subscribe", "subscription", "price", "cost"]):
        return (
            "The Life Shield offers three plans: Free (credit monitoring & score check), "
            "Professional ($69/month — full dispute service + monthly pulls), and "
            "VIP ($129/month — priority service, dedicated advisor, unlimited disputes). "
            "Which plan would work best for your goals?"
        )

    if any(w in msg_lower for w in ["human", "agent", "person", "talk to someone", "escalate"]):
        return (
            "I understand you'd like to speak with a human advisor. I'm flagging this conversation "
            "for escalation. A certified credit advisor will reach out within 1 business day. "
            "Is there anything specific you'd like me to note for them before they contact you?"
        )

    if any(w in msg_lower for w in ["thank", "thanks", "appreciate"]):
        return (
            "You're very welcome! That's exactly what I'm here for. Remember, you have a right "
            "to accurate credit reporting, and I'm in your corner every step of the way. "
            "Is there anything else I can help you with?"
        )

    # Default response
    return (
        "I'm here to help with everything related to your credit health — disputes, score "
        "improvement, understanding your report, billing questions, and more. Could you tell "
        "me a bit more about what you're looking to accomplish? I want to make sure I give you "
        "the most accurate guidance possible."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH & ROOT
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "The Life Shield",
        "version": "2.0.0",
        "modules": ["auth", "billing", "credit", "disputes", "chat"],
    })


@app.route("/", methods=["GET"])
def root():
    return jsonify({"message": "The Life Shield API", "docs": "/health"})


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/v1/auth/register", methods=["POST", "OPTIONS"])
def register():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    if email in USERS:
        return jsonify({"error": "User already exists", "code": "USER_EXISTS"}), 400

    user_id = new_id("usr_")
    USERS[email] = {
        "id": user_id,
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "password": password,
        "role": "client",
        "status": "active",
        "sms_consent": data.get("sms_consent", False),
        "email_consent": data.get("email_consent", True),
        "created_at": now_iso(),
    }

    # Seed initial data
    seed_credit_reports(user_id)
    seed_subscription(user_id)
    DISPUTES[user_id] = []
    CHAT_HISTORY[user_id] = []

    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    TOKENS[access_token] = {"user_id": user_id, "email": email}
    TOKENS[refresh_token] = {"user_id": user_id, "email": email}

    return jsonify({
        "success": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 86400,
        "user_id": user_id,
        "role": "client",
        "user": {
            "id": user_id,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
        },
    }), 200


@app.route("/api/v1/auth/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")

    if email not in USERS:
        return jsonify({"error": "User not found", "code": "USER_NOT_FOUND"}), 404

    user = USERS[email]
    if user["password"] != password:
        return jsonify({"error": "Invalid credentials", "code": "INVALID_PASSWORD"}), 401

    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    TOKENS[access_token] = {"user_id": user["id"], "email": email}
    TOKENS[refresh_token] = {"user_id": user["id"], "email": email}

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 86400,
        "user_id": user["id"],
        "role": user.get("role", "client"),
        "user": {
            "id": user["id"],
            "email": user["email"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
        },
    }), 200


@app.route("/api/v1/auth/me", methods=["GET", "OPTIONS"])
def me():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    return jsonify({
        "id": user["id"],
        "email": user["email"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "role": user.get("role", "client"),
        "status": user.get("status", "active"),
        "sms_consent": user.get("sms_consent", False),
        "email_consent": user.get("email_consent", True),
        "created_at": user.get("created_at", now_iso()),
    }), 200


@app.route("/api/v1/auth/refresh", methods=["POST", "OPTIONS"])
def refresh():
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json() or {}
    rt = data.get("refresh_token", "")
    if rt not in TOKENS:
        return jsonify({"error": "Invalid refresh token"}), 401
    token_data = TOKENS[rt]
    new_token = secrets.token_urlsafe(32)
    TOKENS[new_token] = token_data
    email = token_data["email"]
    user = USERS.get(email, {})
    return jsonify({
        "access_token": new_token,
        "refresh_token": rt,
        "token_type": "bearer",
        "expires_in": 86400,
        "user_id": token_data["user_id"],
        "role": user.get("role", "client"),
    }), 200


@app.route("/api/v1/auth/logout", methods=["POST", "OPTIONS"])
def logout():
    if request.method == "OPTIONS":
        return "", 200
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        TOKENS.pop(token, None)
    return jsonify({"success": True}), 200


@app.route("/api/v1/auth/forgot-password", methods=["POST", "OPTIONS"])
def forgot_password():
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    # Always return success (don't leak user existence)
    return jsonify({"message": "If that email exists, a reset link has been sent."}), 200


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 1 — BILLING & SUBSCRIPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

PLANS = [
    {
        "id": "plan_free",
        "name": "Free",
        "price_monthly": 0,
        "features": ["basic_monitoring", "score_check", "1_bureau_pull_per_month"],
    },
    {
        "id": "plan_professional",
        "name": "Professional",
        "price_monthly": 69,
        "features": [
            "full_dispute_service", "monthly_bureau_pulls", "dispute_letters",
            "score_monitoring", "email_support", "1_free_consultation",
        ],
    },
    {
        "id": "plan_vip",
        "name": "VIP",
        "price_monthly": 129,
        "features": [
            "priority_service", "dedicated_advisor", "unlimited_disputes",
            "weekly_bureau_pulls", "phone_support", "identity_protection",
            "monthly_consultations",
        ],
    },
]


@app.route("/api/v1/products/subscriptions/plans", methods=["GET", "OPTIONS"])
def list_plans():
    if request.method == "OPTIONS":
        return "", 200
    return jsonify({"success": True, "plans": PLANS}), 200


@app.route("/api/v1/products/subscriptions/mine", methods=["GET", "OPTIONS"])
def get_my_subscription():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    sub = SUBSCRIPTIONS.get(user["id"])
    return jsonify({"success": True, "subscription": sub}), 200


@app.route("/api/v1/products/subscriptions", methods=["POST", "OPTIONS"])
def subscribe():
    """Create or upgrade subscription."""
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    data = request.get_json() or {}
    plan_id = data.get("plan_id", "plan_free")
    payment_token = data.get("payment_token", "")

    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan:
        return jsonify({"error": "Invalid plan", "code": "INVALID_PLAN"}), 400

    # In production: charge the card via TRGPay/Stripe
    sub_id = new_id("sub_")
    SUBSCRIPTIONS[user["id"]] = {
        "id": sub_id,
        "user_id": user["id"],
        "plan_id": plan_id,
        "plan_name": plan["name"],
        "price_monthly": plan["price_monthly"],
        "status": "active",
        "started_at": now_iso(),
        "next_billing_at": now_iso(),  # Would be +30 days in prod
        "features": plan["features"],
        "payment_token": payment_token,  # Store reference only
    }

    # Record billing event
    if plan["price_monthly"] > 0:
        if user["id"] not in BILLING_HISTORY:
            BILLING_HISTORY[user["id"]] = []
        BILLING_HISTORY[user["id"]].append({
            "id": new_id("pmt_"),
            "amount": plan["price_monthly"],
            "description": f"{plan['name']} Plan — Monthly",
            "status": "paid",
            "paid_at": now_iso(),
        })

    return jsonify({
        "success": True,
        "subscription_id": sub_id,
        "plan": plan["name"],
        "message": f"Subscribed to {plan['name']} plan successfully.",
    }), 200


@app.route("/api/v1/products/subscriptions/<sub_id>", methods=["PUT", "DELETE", "OPTIONS"])
def manage_subscription(sub_id: str):
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    sub = SUBSCRIPTIONS.get(user["id"])
    if not sub or sub["id"] != sub_id:
        return jsonify({"error": "Subscription not found"}), 404

    if request.method == "PUT":
        # Upgrade / downgrade
        data = request.get_json() or {}
        plan_id = data.get("plan_id")
        if plan_id:
            plan = next((p for p in PLANS if p["id"] == plan_id), None)
            if not plan:
                return jsonify({"error": "Invalid plan"}), 400
            sub["plan_id"] = plan_id
            sub["plan_name"] = plan["name"]
            sub["price_monthly"] = plan["price_monthly"]
            sub["features"] = plan["features"]
        return jsonify({"success": True, "subscription": sub}), 200

    elif request.method == "DELETE":
        # Cancel
        reason = request.args.get("reason", "user_requested")
        sub["status"] = "cancelled"
        sub["cancelled_at"] = now_iso()
        sub["cancel_reason"] = reason
        return jsonify({"success": True, "message": "Subscription cancelled."}), 200


@app.route("/api/v1/billing/payment-methods", methods=["GET", "POST", "OPTIONS"])
def payment_methods():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]
    if uid not in PAYMENT_METHODS:
        PAYMENT_METHODS[uid] = []

    if request.method == "GET":
        return jsonify({
            "success": True,
            "payment_methods": PAYMENT_METHODS[uid],
        }), 200

    elif request.method == "POST":
        data = request.get_json() or {}
        pm = {
            "id": new_id("pm_"),
            "type": data.get("type", "card"),
            "last4": data.get("last4", "****"),
            "brand": data.get("brand", "visa"),
            "exp_month": data.get("exp_month"),
            "exp_year": data.get("exp_year"),
            "is_default": len(PAYMENT_METHODS[uid]) == 0,
            "created_at": now_iso(),
        }
        PAYMENT_METHODS[uid].append(pm)
        return jsonify({"success": True, "payment_method": pm}), 200


@app.route("/api/v1/billing/payment-methods/<pm_id>", methods=["DELETE", "OPTIONS"])
def delete_payment_method(pm_id: str):
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]
    methods = PAYMENT_METHODS.get(uid, [])
    PAYMENT_METHODS[uid] = [m for m in methods if m["id"] != pm_id]
    return jsonify({"success": True}), 200


@app.route("/api/v1/products/billing/history", methods=["GET", "OPTIONS"])
def billing_history():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    limit = int(request.args.get("limit", 20))
    history = BILLING_HISTORY.get(user["id"], [])
    return jsonify({
        "success": True,
        "payments": history[:limit],
        "total": len(history),
    }), 200


@app.route("/api/v1/products", methods=["GET", "OPTIONS"])
def list_products():
    if request.method == "OPTIONS":
        return "", 200
    return jsonify({
        "success": True,
        "products": [
            {"id": p["id"], "name": p["name"], "description": f"{p['name']} credit repair plan",
             "price": p["price_monthly"], "category": "subscription"}
            for p in PLANS
        ],
    }), 200


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 2 — CREDIT REPORTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/v1/credit/summary", methods=["GET", "OPTIONS"])
def credit_summary():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]
    if uid not in CREDIT_REPORTS:
        seed_credit_reports(uid)

    cr = CREDIT_REPORTS[uid]
    disputes = DISPUTES.get(uid, [])
    open_disputes = sum(1 for d in disputes if d["status"] not in ["resolved", "closed"])

    scores = [
        {"bureau": "equifax",    "score": cr["equifax"]["score"],    "pulled_at": cr["equifax"]["pulled_at"]},
        {"bureau": "experian",   "score": cr["experian"]["score"],   "pulled_at": cr["experian"]["pulled_at"]},
        {"bureau": "transunion", "score": cr["transunion"]["score"], "pulled_at": cr["transunion"]["pulled_at"]},
    ]

    avg = sum(s["score"] for s in scores) // 3
    history = cr.get("score_history", [])
    trend = "improving"
    if len(history) >= 2:
        prev_avg = history[-2].get("average", avg)
        trend = "improving" if avg > prev_avg else ("declining" if avg < prev_avg else "stable")

    return jsonify({
        "success": True,
        "client_id": uid,
        "scores": scores,
        "average_score": avg,
        "open_dispute_count": open_disputes,
        "score_trend": trend,
    }), 200


@app.route("/api/v1/credit/reports", methods=["GET", "OPTIONS"])
def credit_reports():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]
    if uid not in CREDIT_REPORTS:
        seed_credit_reports(uid)
    cr = CREDIT_REPORTS[uid]
    return jsonify({
        "success": True,
        "reports": [cr["equifax"], cr["experian"], cr["transunion"]],
    }), 200


@app.route("/api/v1/credit/score-history", methods=["GET", "OPTIONS"])
def credit_score_history():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]
    if uid not in CREDIT_REPORTS:
        seed_credit_reports(uid)
    days = int(request.args.get("days", 90))
    history = CREDIT_REPORTS[uid].get("score_history", [])
    return jsonify({"success": True, "history": history}), 200


@app.route("/api/v1/credit/tradelines", methods=["GET", "OPTIONS"])
def credit_tradelines():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]
    if uid not in CREDIT_REPORTS:
        seed_credit_reports(uid)
    cr = CREDIT_REPORTS[uid]
    return jsonify({
        "success": True,
        "tradelines": cr.get("tradelines", []),
        "inquiries": cr.get("inquiries", []),
        "negative_items": cr.get("negative_items", []),
    }), 200


@app.route("/api/v1/credit/soft-pull", methods=["POST", "OPTIONS"])
def credit_soft_pull():
    """Request a credit report refresh."""
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]
    if uid not in CREDIT_REPORTS:
        seed_credit_reports(uid)

    # Simulate small score movement on refresh
    import random
    cr = CREDIT_REPORTS[uid]
    for bureau in ["equifax", "experian", "transunion"]:
        delta = random.randint(-3, 8)
        cr[bureau]["score"] = max(300, min(850, cr[bureau]["score"] + delta))
        cr[bureau]["pulled_at"] = now_iso()

    # Append to history
    history_entry = {
        "date": now_iso()[:10],
        "equifax": cr["equifax"]["score"],
        "experian": cr["experian"]["score"],
        "transunion": cr["transunion"]["score"],
        "average": (cr["equifax"]["score"] + cr["experian"]["score"] + cr["transunion"]["score"]) // 3,
    }
    cr["score_history"].append(history_entry)

    return jsonify({
        "success": True,
        "message": "Credit report refresh requested. Updated scores available.",
        "scores": {
            "equifax": cr["equifax"]["score"],
            "experian": cr["experian"]["score"],
            "transunion": cr["transunion"]["score"],
        },
    }), 200


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 3 — DISPUTES
# ═══════════════════════════════════════════════════════════════════════════════

DISPUTE_STATUSES = ["pending", "submitted", "investigating", "resolved", "closed"]
DISPUTE_OUTCOMES = ["deleted", "updated", "verified", "unresolved"]


@app.route("/api/v1/disputes", methods=["GET", "POST", "OPTIONS"])
def disputes():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]
    if uid not in DISPUTES:
        DISPUTES[uid] = []

    if request.method == "GET":
        status_filter = request.args.get("status")
        d_list = DISPUTES[uid]
        if status_filter:
            d_list = [d for d in d_list if d["status"] == status_filter]
        return jsonify({
            "success": True,
            "disputes": d_list,
            "total": len(d_list),
        }), 200

    elif request.method == "POST":
        data = request.get_json() or {}
        tradeline_id = data.get("tradeline_id", "")
        bureau = data.get("bureau", "equifax")
        dispute_reason = data.get("dispute_reason", "")
        client_statement = data.get("client_statement", "")

        if not dispute_reason:
            return jsonify({"error": "dispute_reason is required"}), 400

        dispute_id = new_id("dsp_")
        dispute = {
            "id": dispute_id,
            "user_id": uid,
            "tradeline_id": tradeline_id,
            "bureau": bureau,
            "dispute_reason": dispute_reason,
            "client_statement": client_statement,
            "status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "investigation_deadline": None,
            "outcome": None,
            "letter": {
                "content": _generate_dispute_letter(user, tradeline_id, bureau, dispute_reason, client_statement),
                "status": "draft",
                "generated_at": now_iso(),
            },
            "bureau_responses": [],
        }
        DISPUTES[uid].append(dispute)

        return jsonify({
            "success": True,
            "dispute_id": dispute_id,
            "status": "pending",
            "message": f"Dispute filed against {bureau.title()}. Letter generated and ready for review.",
        }), 201


@app.route("/api/v1/disputes/<dispute_id>", methods=["GET", "PUT", "OPTIONS"])
def dispute_detail(dispute_id: str):
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]
    disputes_list = DISPUTES.get(uid, [])
    dispute = next((d for d in disputes_list if d["id"] == dispute_id), None)
    if not dispute:
        return jsonify({"error": "Dispute not found"}), 404

    if request.method == "GET":
        return jsonify({
            "success": True,
            "dispute": dispute,
            "letter": dispute.get("letter"),
            "bureau_responses": dispute.get("bureau_responses", []),
        }), 200

    elif request.method == "PUT":
        data = request.get_json() or {}
        # Allow staff/admin to update status
        new_status = data.get("status")
        if new_status and new_status in DISPUTE_STATUSES:
            dispute["status"] = new_status
            dispute["updated_at"] = now_iso()
        outcome = data.get("outcome")
        if outcome and outcome in DISPUTE_OUTCOMES:
            dispute["outcome"] = outcome
        if "notes" in data:
            dispute["notes"] = data["notes"]
        return jsonify({"success": True, "dispute": dispute}), 200


@app.route("/api/v1/disputes/<dispute_id>/approve-letter", methods=["POST", "OPTIONS"])
def approve_dispute_letter(dispute_id: str):
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]
    disputes_list = DISPUTES.get(uid, [])
    dispute = next((d for d in disputes_list if d["id"] == dispute_id), None)
    if not dispute:
        return jsonify({"error": "Dispute not found"}), 404

    data = request.get_json() or {}
    approved = data.get("approved", True)
    notes = data.get("notes", "")

    if approved:
        dispute["letter"]["status"] = "approved"
        dispute["status"] = "submitted"
        dispute["updated_at"] = now_iso()
        dispute["investigation_deadline"] = now_iso()  # +30 days in prod
    else:
        dispute["letter"]["status"] = "revision_requested"
        if notes:
            dispute["letter"]["revision_notes"] = notes

    return jsonify({
        "success": True,
        "dispute_id": dispute_id,
        "letter_status": dispute["letter"]["status"],
        "dispute_status": dispute["status"],
    }), 200


def _generate_dispute_letter(user: dict, tradeline_id: str, bureau: str, reason: str, statement: str) -> str:
    """Generate a professional FCRA-compliant dispute letter."""
    bureau_name = bureau.title()
    full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    bureau_addresses = {
        "Equifax":    "P.O. Box 740256, Atlanta, GA 30374-0256",
        "Experian":   "P.O. Box 4500, Allen, TX 75013",
        "Transunion": "P.O. Box 2000, Chester, PA 19016",
    }
    addr = bureau_addresses.get(bureau_name, f"{bureau_name} Consumer Division")

    return f"""[DATE]

{bureau_name} Consumer Dispute Center
{addr}

Re: Dispute of Inaccurate Credit Information

To Whom It May Concern,

I am writing to formally dispute inaccurate information appearing on my credit report. 
My name is {full_name} and I am exercising my rights under the Fair Credit Reporting Act (FCRA), 
15 U.S.C. § 1681 et seq., to request correction of inaccurate information.

ITEM IN DISPUTE:
Account/Item ID: {tradeline_id or "See attached report"}
Bureau: {bureau_name}
Reason for Dispute: {reason}

CLIENT STATEMENT:
{statement or "This account contains inaccurate information that I dispute in its entirety."}

Under Section 611 of the FCRA, you are required to conduct a reasonable investigation into this 
dispute and correct or delete any information that cannot be verified within 30 days of receipt 
of this letter.

Please investigate this item and take one of the following actions:
1. Delete the item if it cannot be verified
2. Correct the information if it is inaccurate
3. Provide written notice of the results of your investigation

Please send me a free copy of my updated credit report once the dispute has been resolved.

Sincerely,
{full_name}

Enclosures: Copy of government-issued ID, Proof of address, Relevant supporting documentation
"""


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 4 — TIM SHAW AI CHAT
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/v1/agents/chat", methods=["POST", "OPTIONS"])
def agent_chat():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]
    if uid not in CHAT_HISTORY:
        CHAT_HISTORY[uid] = []

    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    channel = data.get("channel", "portal_chat")

    if not message:
        return jsonify({"error": "message is required"}), 400

    # Store inbound message
    msg_id = new_id("msg_")
    inbound = {
        "id": msg_id,
        "direction": "inbound",
        "content": message,
        "channel": channel,
        "created_at": now_iso(),
        "agent": None,
    }
    CHAT_HISTORY[uid].append(inbound)

    # Generate Tim Shaw response
    response_text = tim_shaw_respond(message, CHAT_HISTORY[uid])
    requires_human = any(w in message.lower() for w in ["human", "agent", "person", "talk to someone", "escalate"])

    # Store outbound response
    resp_id = new_id("msg_")
    outbound = {
        "id": resp_id,
        "direction": "outbound",
        "content": response_text,
        "channel": channel,
        "created_at": now_iso(),
        "agent": "Tim Shaw",
    }
    CHAT_HISTORY[uid].append(outbound)

    return jsonify({
        "success": True,
        "message_id": resp_id,
        "agent": "Tim Shaw",
        "response": response_text,
        "channel": channel,
        "requires_human": requires_human,
        "timestamp": now_iso(),
    }), 200


@app.route("/api/v1/agents/history/<client_id>", methods=["GET", "OPTIONS"])
def agent_history(client_id: str):
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]
    # Clients can only see their own history
    target_id = uid  # Admin override would go here
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    history = CHAT_HISTORY.get(target_id, [])
    paged = history[offset: offset + limit]
    return jsonify({
        "success": True,
        "messages": paged,
        "total": len(history),
        "limit": limit,
        "offset": offset,
    }), 200


@app.route("/api/v1/agents/status", methods=["GET", "OPTIONS"])
def agent_status():
    if request.method == "OPTIONS":
        return "", 200
    return jsonify({
        "agent": "Tim Shaw",
        "status": "online",
        "expected_response_time": "instant",
        "channels": ["portal_chat", "sms", "email"],
        "disclosure": (
            "Tim Shaw is an AI-powered credit advisor. The information provided is for "
            "educational purposes and does not constitute legal or financial advice. "
            "The Life Shield is not a law firm."
        ),
    }), 200


@app.route("/api/v1/agents/escalate", methods=["POST", "OPTIONS"])
def agent_escalate():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    data = request.get_json() or {}
    reason = data.get("reason", "user_requested")
    message = data.get("message", "")
    escalation_id = new_id("esc_")
    return jsonify({
        "success": True,
        "escalation_id": escalation_id,
        "message": (
            "Your request has been escalated to a human advisor. "
            "You'll hear back within 1 business day."
        ),
    }), 200


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENTS & DASHBOARD (portal needs these)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/v1/clients/me", methods=["GET", "PUT", "OPTIONS"])
def client_profile():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err

    if request.method == "GET":
        uid = user["id"]
        sub = SUBSCRIPTIONS.get(uid)
        return jsonify({
            "user_id": uid,
            "email": user["email"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "phone": user.get("phone"),
            "subscription_plan": sub["plan_name"] if sub else "Free",
            "status": user.get("status", "active"),
            "address": user.get("address", {}),
            "sms_consent": user.get("sms_consent", False),
            "email_consent": user.get("email_consent", True),
            "voice_consent": user.get("voice_consent", False),
            "created_at": user.get("created_at", now_iso()),
        }), 200

    elif request.method == "PUT":
        data = request.get_json() or {}
        for field in ["first_name", "last_name", "phone", "address"]:
            if field in data:
                user[field] = data[field]
        return jsonify({"success": True, "message": "Profile updated."}), 200


@app.route("/api/v1/clients/me/dashboard", methods=["GET", "OPTIONS"])
def client_dashboard():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    uid = user["id"]

    if uid not in CREDIT_REPORTS:
        seed_credit_reports(uid)
    cr = CREDIT_REPORTS[uid]

    disputes = DISPUTES.get(uid, [])
    active_disputes = sum(1 for d in disputes if d["status"] not in ["resolved", "closed"])
    resolved_disputes = sum(1 for d in disputes if d["status"] == "resolved")

    sub = SUBSCRIPTIONS.get(uid)
    chat = CHAT_HISTORY.get(uid, [])

    return jsonify({
        "success": True,
        "data": {
            "scores": {
                "equifax":    {"score": cr["equifax"]["score"],    "pulled_at": cr["equifax"]["pulled_at"]},
                "experian":   {"score": cr["experian"]["score"],   "pulled_at": cr["experian"]["pulled_at"]},
                "transunion": {"score": cr["transunion"]["score"], "pulled_at": cr["transunion"]["pulled_at"]},
            },
            "active_disputes": active_disputes,
            "resolved_disputes": resolved_disputes,
            "next_appointment": None,
            "recent_activity": [
                {
                    "id": m["id"],
                    "channel": m["channel"],
                    "summary": m["content"][:80] + "..." if len(m["content"]) > 80 else m["content"],
                    "created_at": m["created_at"],
                }
                for m in reversed(chat[-5:])
            ],
            "documents_pending": 0,
            "subscription": {
                "plan": sub["plan_name"] if sub else "Free",
                "status": sub["status"] if sub else "active",
            } if sub else None,
        },
    }), 200


@app.route("/api/v1/clients/me/consent", methods=["POST", "OPTIONS"])
def update_consent():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    data = request.get_json() or {}
    for field in ["sms_consent", "email_consent", "voice_consent"]:
        if field in data:
            user[field] = data[field]
    return jsonify({"success": True}), 200


@app.route("/api/v1/clients/me/documents", methods=["GET", "OPTIONS"])
def client_documents():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    return jsonify({"success": True, "documents": []}), 200


@app.route("/api/v1/clients/me/appointments", methods=["GET", "POST", "OPTIONS"])
def client_appointments():
    if request.method == "OPTIONS":
        return "", 200
    user, err = get_auth_user()
    if err:
        return err
    if request.method == "GET":
        return jsonify({"success": True, "appointments": []}), 200
    elif request.method == "POST":
        data = request.get_json() or {}
        apt_id = new_id("apt_")
        return jsonify({"success": True, "appointment_id": apt_id}), 201


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🛡️  The Life Shield API starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
