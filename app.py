# -*- coding: utf-8 -*-
"""机时预订网站后端。Flask + SQLite。"""

import os
import re
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "booking.db")

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.json.ensure_ascii = False
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# ============================ 数据库 ============================

SEED_DEVICES = [
    # (name, ip, location, os, cpu, motherboard, motherboard_vendor, memory)
    ("sza-psg-1card-01", "10.6.128.1", "深圳", "Ubuntu 20.04.6 LTS", "Intel i7-13701K", "PRIME Z790-P WIFI", "华硕主板", "64GiB"),
    ("sza-psg-1card-02", "10.6.128.2", "深圳", "Ubuntu 20.04.6 LTS", "Intel i7-13702K", "PRIME Z790-P WIFI", "华硕主板", "64GiB"),
    ("sza-psg-1card-03", "10.6.128.3", "深圳", "Ubuntu 20.04.6 LTS", "Intel i7-13703K", "PRIME Z790-P WIFI", "华硕主板", "64GiB"),
    ("sza-psg-1card-04", "10.6.128.4", "深圳", "Ubuntu 20.04.6 LTS", "AMD 7960X", "TRX50 AERO D", "技嘉", "64GB"),
    ("sza-psg-1card-05", "10.6.128.5", "深圳", "Ubuntu 24.04.4 LTS", "Intel i7-13700K", "PRIME Z790-P WIFI", "华硕主板", "64GB"),
    ("sza-psg-1card-06", "10.6.128.6", "深圳", "Ubuntu 24.04.3 LTS", "Intel i7-13700k", "PRIME Z790-P WIFI", "ASUSTeK", "128GiB"),
    ("sza-psg-1card-07", "10.6.128.7", "深圳", "Ubuntu 20.04.6 LTS", "Intel i7-13700k", "PRIME Z790-P WIFI", "ASUSTeK", "64GiB"),
    ("sza-psg-1card-08", "10.6.128.8", "深圳", "Ubuntu 20.04.6 LTS", "Intel i7-13700K", "PRIME Z790-P WIFI", "ASUSTeK", "64GiB"),
    ("sza-psg-1card-09", "10.6.128.9", "深圳", "Ubuntu 20.04.6 LTS", "Intel i7-13700K", "PRIME Z790-P WIFI", "ASUSTeK", "64GiB"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    ip TEXT NOT NULL,
    location TEXT DEFAULT '深圳',
    os TEXT,
    cpu TEXT,
    motherboard TEXT,
    motherboard_vendor TEXT,
    memory TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name TEXT NOT NULL,
    date TEXT NOT NULL,
    hour INTEGER NOT NULL,
    username TEXT NOT NULL,
    created_at TEXT,
    UNIQUE(device_name, date, hour)
);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(username, date);
CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS power_state (
    device_id INTEGER PRIMARY KEY,
    device_name TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'unknown',
    updated_at TEXT
);
"""


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # 种子用户 jimmy.xie（初始密码 123456）
    if not conn.execute("SELECT 1 FROM users WHERE username=?", ("jimmy.xie",)).fetchone():
        conn.execute(
            "INSERT INTO users(username, password_hash, display_name, created_at) VALUES (?,?,?,?)",
            ("jimmy.xie", generate_password_hash("123456"), "jimmy.xie", now_str()),
        )
    # 已有数据库只迁移一次，之后用户在账户弹窗中修改的密码不会被重启覆盖。
    password_migration = "seed_password_jimmy_xie_123456_v1"
    if not conn.execute("SELECT 1 FROM app_meta WHERE key=?", (password_migration,)).fetchone():
        conn.execute(
            "UPDATE users SET password_hash=? WHERE username=?",
            (generate_password_hash("123456"), "jimmy.xie"),
        )
        conn.execute(
            "INSERT INTO app_meta(key, value, updated_at) VALUES (?,?,?)",
            (password_migration, "applied", now_str()),
        )
    # 种子设备
    if conn.execute("SELECT COUNT(*) AS c FROM devices").fetchone()["c"] == 0:
        for d in SEED_DEVICES:
            conn.execute(
                "INSERT INTO devices(name, ip, location, os, cpu, motherboard, motherboard_vendor, memory, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (*d, now_str()),
            )
    # 为每台设备初始化本地虚拟电源状态；已有状态保持不变。
    for device in conn.execute("SELECT id, name FROM devices").fetchall():
        conn.execute(
            "INSERT OR IGNORE INTO power_state(device_id, device_name, state) VALUES (?,?,?)",
            (device["id"], device["name"], "unknown"),
        )
    conn.commit()
    conn.close()


# ============================ 认证装饰器 ============================


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return jsonify({"error": "未登录"}), 401
        return f(*args, **kwargs)

    return wrapper


def login_required_page(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapper


# ============================ 页面路由 ============================


@app.route("/")
def index():
    return redirect(url_for("booking"))


@app.route("/login")
def login():
    if "username" in session:
        return redirect(url_for("booking"))
    return render_template("login.html")


@app.route("/register")
def register():
    if "username" in session:
        return redirect(url_for("booking"))
    return render_template("register.html")


@app.route("/booking")
@login_required_page
def booking():
    return render_template("booking.html", username=session["username"])


@app.route("/devices")
@login_required_page
def devices_page():
    return render_template("devices.html", username=session["username"])


@app.route("/iot")
@login_required_page
def iot_page():
    return render_template("iot.html", username=session["username"])


@app.route("/my")
@login_required_page
def my_page():
    return render_template("my_bookings.html", username=session["username"])


# ============================ 认证 API ============================


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    if not re.fullmatch(r"[A-Za-z0-9._-]+", username):
        return jsonify({"error": "用户名只能包含字母、数字、点、下划线、中划线"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码至少 6 位"}), 400
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        return jsonify({"error": "用户名已存在"}), 409
    db.execute(
        "INSERT INTO users(username, password_hash, display_name, created_at) VALUES (?,?,?,?)",
        (username, generate_password_hash(password), username, now_str()),
    )
    db.commit()
    session.clear()
    session["username"] = username
    return jsonify({"ok": True, "username": username})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    row = get_db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "用户名或密码错误"}), 401
    session.clear()
    session.permanent = bool(data.get("remember"))
    session["username"] = username
    return jsonify({"ok": True, "username": username, "remember": session.permanent})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/me")
def api_me():
    return jsonify({"username": session.get("username")})


@app.route("/api/change_password", methods=["POST"])
@login_required
def api_change_password():
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""
    confirm_password = data.get("confirm_password") or ""
    if not current_password or not new_password or not confirm_password:
        return jsonify({"error": "请完整填写密码"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "新密码至少 6 位"}), 400
    if new_password != confirm_password:
        return jsonify({"error": "两次输入的新密码不一致"}), 400
    if current_password == new_password:
        return jsonify({"error": "新密码不能与当前密码相同"}), 400
    db = get_db()
    user = db.execute(
        "SELECT id, password_hash FROM users WHERE username=?",
        (session["username"],),
    ).fetchone()
    if not user or not check_password_hash(user["password_hash"], current_password):
        return jsonify({"error": "当前密码不正确"}), 400
    db.execute(
        "UPDATE users SET password_hash=? WHERE id=?",
        (generate_password_hash(new_password), user["id"]),
    )
    db.commit()
    return jsonify({"ok": True})


# ============================ 设备 CRUD API ============================


DEVICE_FIELDS = ["name", "ip", "location", "os", "cpu", "motherboard", "motherboard_vendor", "memory"]


def device_payload(row):
    return {k: row[k] for k in ["id", "name", "ip", "location", "os", "cpu", "motherboard", "motherboard_vendor", "memory"]}


@app.route("/api/devices", methods=["GET"])
@login_required
def api_list_devices():
    rows = get_db().execute("SELECT * FROM devices ORDER BY name").fetchall()
    return jsonify({"devices": [device_payload(r) for r in rows]})


@app.route("/api/devices", methods=["POST"])
@login_required
def api_create_device():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    ip = (data.get("ip") or "").strip()
    if not name or not ip:
        return jsonify({"error": "主机名和 IP 不能为空"}), 400
    db = get_db()
    if db.execute("SELECT 1 FROM devices WHERE name=?", (name,)).fetchone():
        return jsonify({"error": "主机名已存在"}), 409
    db.execute(
        "INSERT INTO devices(name, ip, location, os, cpu, motherboard, motherboard_vendor, memory, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            name, ip,
            (data.get("location") or "深圳").strip(),
            (data.get("os") or "").strip(),
            (data.get("cpu") or "").strip(),
            (data.get("motherboard") or "").strip(),
            (data.get("motherboard_vendor") or "").strip(),
            (data.get("memory") or "").strip(),
            now_str(),
        ),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/devices/<int:device_id>", methods=["PUT"])
@login_required
def api_update_device(device_id):
    data = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        return jsonify({"error": "设备不存在"}), 404
    new_name = (data.get("name") or row["name"]).strip()
    new_ip = (data.get("ip") or row["ip"]).strip()
    if not new_name or not new_ip:
        return jsonify({"error": "主机名和 IP 不能为空"}), 400
    dup = db.execute("SELECT 1 FROM devices WHERE name=? AND id<>?", (new_name, device_id)).fetchone()
    if dup:
        return jsonify({"error": "主机名已存在"}), 409
    vals = {}
    for k in ["name", "ip", "location", "os", "cpu", "motherboard", "motherboard_vendor", "memory"]:
        vals[k] = (data.get(k) if data.get(k) is not None else row[k] or "").strip()
    vals["name"], vals["ip"] = new_name, new_ip
    db.execute(
        "UPDATE devices SET name=?, ip=?, location=?, os=?, cpu=?, motherboard=?, motherboard_vendor=?, memory=? WHERE id=?",
        (vals["name"], vals["ip"], vals["location"], vals["os"], vals["cpu"],
         vals["motherboard"], vals["motherboard_vendor"], vals["memory"], device_id),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/devices/<int:device_id>", methods=["DELETE"])
@login_required
def api_delete_device(device_id):
    db = get_db()
    row = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        return jsonify({"error": "设备不存在"}), 404
    db.execute("DELETE FROM bookings WHERE device_name=?", (row["name"],))
    db.execute("DELETE FROM power_state WHERE device_id=?", (device_id,))
    db.execute("DELETE FROM devices WHERE id=?", (device_id,))
    db.commit()
    return jsonify({"ok": True})


# ============================ 预订 API ============================


def slot_is_past(date_str, hour):
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if date_str < today:
        return True
    if date_str == today and hour <= now.hour:
        return True
    return False


def iter_dates(start, end):
    d = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    out = []
    while d <= e:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


@app.route("/api/bookings", methods=["GET"])
@login_required
def api_get_bookings():
    date = request.args.get("date") or today_str()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return jsonify({"error": "日期格式错误"}), 400
    db = get_db()
    devices = db.execute("SELECT name FROM devices ORDER BY name").fetchall()
    rows = db.execute("SELECT device_name, hour, username FROM bookings WHERE date=?", (date,)).fetchall()
    slot_map = {}
    for r in rows:
        slot_map.setdefault(r["device_name"], {})[str(r["hour"])] = r["username"]
    result = []
    for d in devices:
        result.append({"name": d["name"], "slots": slot_map.get(d["name"], {})})
    return jsonify({"date": date, "current_user": session["username"], "devices": result})


def _parse_range_body(data):
    device_names = data.get("device_names") or []
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    hours = data.get("hours") or []
    if not isinstance(device_names, list) or not device_names:
        return None, None, None, None, "请选择设备"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_date or "") or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_date or ""):
        return None, None, None, None, "日期格式错误"
    if not isinstance(hours, list) or not hours:
        return None, None, None, None, "请选择小时"
    hours = [int(h) for h in hours if isinstance(h, int) or (isinstance(h, str) and h.isdigit())]
    if any(h < 0 or h > 23 for h in hours):
        return None, None, None, None, "小时范围错误"
    return device_names, start_date, end_date, sorted(set(hours)), None


@app.route("/api/bookings", methods=["POST"])
@login_required
def api_book():
    data = request.get_json(silent=True) or {}
    device_names, start_date, end_date, hours, err = _parse_range_body(data)
    if err:
        return jsonify({"error": err}), 400
    username = session["username"]
    db = get_db()
    booked = skipped = 0
    for dev in device_names:
        for date in iter_dates(start_date, end_date):
            for h in hours:
                if slot_is_past(date, h):
                    skipped += 1
                    continue
                try:
                    db.execute(
                        "INSERT INTO bookings(device_name, date, hour, username, created_at) VALUES (?,?,?,?,?)",
                        (dev, date, h, username, now_str()),
                    )
                    booked += 1
                except sqlite3.IntegrityError:
                    skipped += 1
    db.commit()
    return jsonify({"ok": True, "booked": booked, "skipped": skipped})


@app.route("/api/bookings", methods=["DELETE"])
@login_required
def api_cancel():
    data = request.get_json(silent=True) or {}
    device_names, start_date, end_date, hours, err = _parse_range_body(data)
    if err:
        return jsonify({"error": err}), 400
    username = session["username"]
    db = get_db()
    cancelled = 0
    for dev in device_names:
        for date in iter_dates(start_date, end_date):
            for h in hours:
                cur = db.execute(
                    "DELETE FROM bookings WHERE device_name=? AND date=? AND hour=? AND username=?",
                    (dev, date, h, username),
                )
                cancelled += cur.rowcount
    db.commit()
    return jsonify({"ok": True, "cancelled": cancelled})


@app.route("/api/my_bookings", methods=["GET"])
@login_required
def api_my_bookings():
    db = get_db()
    rows = db.execute(
        "SELECT device_name, date, hour FROM bookings WHERE username=? ORDER BY date, device_name, hour",
        (session["username"],),
    ).fetchall()
    grouped = {}
    for r in rows:
        key = (r["device_name"], r["date"])
        grouped.setdefault(key, []).append(r["hour"])
    result = [{"device_name": k[0], "date": k[1], "hours": sorted(v)} for k, v in grouped.items()]
    return jsonify({"bookings": result})


# ============================ 互联设备（本地虚拟电源）============================


def load_power_states(db):
    rows = db.execute(
        "SELECT device_id, state, updated_at FROM power_state"
    ).fetchall()
    return {row["device_id"]: row for row in rows}


@app.route("/api/iot/devices", methods=["GET"])
@login_required
def api_iot_devices():
    db = get_db()
    hosts = db.execute("SELECT id, name, ip, location FROM devices ORDER BY name").fetchall()
    states = load_power_states(db)
    devices = []

    for host in hosts:
        saved = states.get(host["id"])
        state = saved["state"] if saved and saved["state"] in ("on", "off") else "unknown"
        devices.append({
            "id": host["id"],
            "name": host["name"],
            "ip": host["ip"],
            "location": host["location"] or "深圳",
            "state": state,
            "state_updated_at": saved["updated_at"] if saved else None,
        })

    return jsonify({
        "devices": devices,
        "summary": {
            "total": len(devices),
            "on": sum(1 for item in devices if item["state"] == "on"),
            "off": sum(1 for item in devices if item["state"] == "off"),
            "unknown": sum(1 for item in devices if item["state"] == "unknown"),
        },
    })


@app.route("/api/iot/<int:device_id>/<action>", methods=["POST"])
@login_required
def api_iot_action(device_id, action):
    if action not in ("on", "off"):
        return jsonify({"error": "不支持的操作"}), 400
    db = get_db()
    host = db.execute(
        "SELECT id, name, ip FROM devices WHERE id=?", (device_id,)
    ).fetchone()
    if not host:
        return jsonify({"error": "设备不存在"}), 404

    updated_at = now_str()
    db.execute(
        "INSERT INTO power_state(device_id, device_name, state, updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(device_id) DO UPDATE SET "
        "device_name=excluded.device_name, state=excluded.state, updated_at=excluded.updated_at",
        (host["id"], host["name"], action, updated_at),
    )
    db.commit()
    return jsonify({
        "ok": True,
        "device": {
            "id": host["id"],
            "name": host["name"],
            "ip": host["ip"],
            "state": action,
            "state_updated_at": updated_at,
        },
    })


# ============================ 启动 ============================


if __name__ == "__main__":
    init_db()
    app.run(host=config.HOST, port=config.PORT, debug=False)
