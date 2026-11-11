# -*- coding: utf-8 -*-
"""机时预订网站配置。可通过环境变量覆盖敏感项。"""

import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_secret_key():
    configured = os.environ.get("SECRET_KEY")
    if configured:
        return configured
    path = os.path.join(BASE_DIR, ".secret_key")
    try:
        with open(path, "r", encoding="ascii") as fh:
            saved = fh.read().strip()
            if saved:
                return saved
    except FileNotFoundError:
        pass
    generated = secrets.token_hex(32)
    try:
        with open(path, "x", encoding="ascii") as fh:
            fh.write(generated)
        return generated
    except FileExistsError:
        with open(path, "r", encoding="ascii") as fh:
            return fh.read().strip()


# 首次运行生成并持久化，保证网站重启后保持登录仍然有效。
SECRET_KEY = load_secret_key()

# 监听地址与端口
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
