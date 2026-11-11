# -*- coding: utf-8 -*-
"""机时预订网站后端。Flask + SQLite。"""

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import config
import mi_cloud

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "booking.db")
MI_POWER_PATH = os.path.join(BASE_DIR, "mi_power.json")
MI_CLOUD_PATH = os.path.join(BASE_DIR, "mi_cloud.json")
MI_CLOUD_TIMEOUT = float(os.environ.get("MI_CLOUD_TIMEOUT", "15"))

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

SEED_USERS = [
    "jimmy.xie",
    "sp.jackie.hai",
    "sandy.liang",
    "qingang.wang",
    "junmen.chen",
    "zhengbo.huang",
    "xiaojie.lv",
    "xiaoni.mai",
    "chongwu.peng",
    "zhilong.sun",
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
    # 种子用户（初始密码 123456）
    for username in SEED_USERS:
        if not conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            conn.execute(
                "INSERT INTO users(username, password_hash, display_name, created_at) VALUES (?,?,?,?)",
                (username, generate_password_hash("123456"), username, now_str()),
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


# ============================ 互联设备（小米电源控制）============================


def load_power_states(db):
    rows = db.execute(
        "SELECT device_id, state, updated_at FROM power_state"
    ).fetchall()
    return {row["device_id"]: row for row in rows}


def load_mi_power_config():
    try:
        with open(MI_POWER_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def get_mi_mapping(config, device_name):
    devices = config.get("devices") if isinstance(config.get("devices"), dict) else {}
    return devices.get(device_name)


def get_mi_cloud():
    return mi_cloud.MiCloud(MI_CLOUD_PATH)


def query_mi_power_state(config, mapping):
    did = str(mapping.get("did", ""))
    if not did:
        raise RuntimeError("该设备未配置小米 did")
    siid = int(mapping.get("siid", 2))
    piid = int(mapping.get("piid", 1))
    try:
        return bool(get_mi_cloud().get_prop(did, siid, piid, timeout=MI_CLOUD_TIMEOUT))
    except mi_cloud.MiCloudException as exc:
        raise RuntimeError(str(exc)) from exc


def set_mi_power_state(mapping, target_on):
    did = str(mapping.get("did", ""))
    if not did:
        raise RuntimeError("该设备未配置小米 did")
    siid = int(mapping.get("siid", 2))
    piid = int(mapping.get("piid", 1))
    try:
        get_mi_cloud().set_prop(did, siid, piid, bool(target_on), timeout=MI_CLOUD_TIMEOUT)
    except mi_cloud.MiCloudException as exc:
        raise RuntimeError(str(exc)) from exc


def save_power_state(db, device_id, device_name, state, updated_at):
    db.execute(
        "INSERT INTO power_state(device_id, device_name, state, updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(device_id) DO UPDATE SET "
        "device_name=excluded.device_name, state=excluded.state, updated_at=excluded.updated_at",
        (device_id, device_name, state, updated_at),
    )


@app.route("/api/iot/devices", methods=["GET"])
@login_required
def api_iot_devices():
    db = get_db()
    hosts = db.execute("SELECT id, name, ip, location FROM devices ORDER BY name").fetchall()
    states = load_power_states(db)
    config = load_mi_power_config()
    control_enabled = bool(config.get("enabled", False))
    devices = []

    for host in hosts:
        mapping = get_mi_mapping(config, host["name"])
        saved = states.get(host["id"])
        if not mapping:
            state = "unconfigured"
            error = None
            state_updated_at = saved["updated_at"] if saved else None
        else:
            try:
                power_on = query_mi_power_state(config, mapping)
                state = "on" if power_on else "off"
                error = None
                state_updated_at = now_str()
                save_power_state(db, host["id"], host["name"], state, state_updated_at)
            except RuntimeError as exc:
                state = "error"
                error = str(exc)
                state_updated_at = saved["updated_at"] if saved else None

        devices.append({
            "id": host["id"],
            "name": host["name"],
            "ip": host["ip"],
            "location": host["location"] or "深圳",
            "configured": bool(mapping),
            "state": state,
            "error": error,
            "state_updated_at": state_updated_at,
        })

    db.commit()
    return jsonify({
        "devices": devices,
        "summary": {
            "total": len(devices),
            "on": sum(1 for item in devices if item["state"] == "on"),
            "off": sum(1 for item in devices if item["state"] == "off"),
            "unknown": sum(1 for item in devices if item["state"] in ("unknown", "error")),
            "unconfigured": sum(1 for item in devices if item["state"] == "unconfigured"),
        },
        "control_enabled": control_enabled,
        "dry_run": not control_enabled,
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

    config = load_mi_power_config()
    mapping = get_mi_mapping(config, host["name"])
    if not mapping:
        return jsonify({"error": f"{host['name']} 尚未配置小米电源映射"}), 409

    target_on = action == "on"
    control_enabled = bool(config.get("enabled", False))
    dry_run = not control_enabled

    if not dry_run:
        try:
            set_mi_power_state(mapping, target_on)
        except RuntimeError as exc:
            return jsonify({"error": f"控制失败：{exc}"}), 502

        updated_at = now_str()
        save_power_state(db, host["id"], host["name"], action, updated_at)
        db.commit()
        return jsonify({
            "ok": True,
            "dry_run": False,
            "device": {
                "id": host["id"],
                "name": host["name"],
                "ip": host["ip"],
                "state": action,
                "state_updated_at": updated_at,
            },
        })

    return jsonify({
        "ok": True,
        "dry_run": True,
        "message": f"演练模式：已模拟{('上电' if target_on else '断电')}，未对真实设备下发指令",
        "device": {
            "id": host["id"],
            "name": host["name"],
            "ip": host["ip"],
            "state": None,
            "state_updated_at": None,
        },
    })


# ============================ 启动 ============================


def get_lan_ip():
    """探测本机局域网 IPv4，失败时返回 None。"""
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.3)
        # 连接不会真正发送数据，只是让系统选出出口网卡地址。
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return None


if __name__ == "__main__":
    init_db()
    lan_ip = get_lan_ip()
    print("=" * 48)
    print("深圳 PC 机时预订系统")
    print(f"本机访问：   http://127.0.0.1:{config.PORT}/")
    if lan_ip:
        print(f"局域网访问： http://{lan_ip}:{config.PORT}/")
    else:
        print("局域网访问： 未能自动获取，请运行 ip addr 或 hostname -I 查看")
    print("=" * 48)
    app.run(host=config.HOST, port=config.PORT, debug=False)
