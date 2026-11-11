# -*- coding: utf-8 -*-
"""小米云 MIoT 控制封装（米家 App 同款云端通路）。

登录与加密请求逻辑参考：
- https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor  (MIT)
- https://github.com/al-one/hass-xiaomi-miot  (Apache-2.0)

本模块自包含，不依赖 micloud，仅依赖 requests 与 pycryptodome。
真实账号 / Token 只写入被 .gitignore 忽略的本地 JSON，请勿提交。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import re
import string
import time
from urllib.parse import parse_qs, urlparse

import requests

try:
    from Crypto.Cipher import ARC4
except ImportError:  # pragma: no cover
    from Cryptodome.Cipher import ARC4


class MiCloudException(Exception):
    """小米云登录或请求异常。"""


class MiCloud:
    """一个可直接用于小米云 MIoT 读写的最小客户端。"""

    def __init__(self, config_path: str | None = None):
        self.config_path = config_path
        self.session = requests.Session()

        self.username: str | None = None
        self.country = "cn"
        self.user_id: str | None = None
        self.ssecurity: str | None = None
        self.c_user_id: str | None = None
        self.pass_token: str | None = None
        self.service_token: str | None = None

        self.agent_id = "".join(random.choice("ABCDEF") for _ in range(13))
        self.client_id = "".join(random.choice(string.ascii_lowercase) for _ in range(6))
        self.useragent = (
            f"Android-7.1.1-1.0.0-ONEPLUS A3010-136-{self.agent_id} "
            "APP/xiaomi.smarthome APPV/62830"
        )
        self.locale = "zh_CN"
        self.timezone = "GMT+08:00"

        if config_path:
            self.load()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def load(self) -> None:
        if not self.config_path or not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        self.username = data.get("username")
        self.country = data.get("country", "cn")
        self.user_id = data.get("user_id")
        self.ssecurity = data.get("ssecurity")
        self.c_user_id = data.get("c_user_id")
        self.pass_token = data.get("pass_token")
        self.service_token = data.get("service_token")

    def save(self) -> None:
        if not self.config_path:
            return
        payload = {
            "username": self.username,
            "country": self.country,
            "user_id": self.user_id,
            "ssecurity": self.ssecurity,
            "c_user_id": self.c_user_id,
            "pass_token": self.pass_token,
            "service_token": self.service_token,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        tmp = f"{self.config_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.config_path)

    @property
    def is_configured(self) -> bool:
        return bool(self.service_token and self.user_id and self.ssecurity)

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------
    def _init_login_cookies(self) -> None:
        self.session.cookies.set("sdkVersion", "accountsdk-18.8.15", domain="mi.com")
        self.session.cookies.set("sdkVersion", "accountsdk-18.8.15", domain="xiaomi.com")
        self.session.cookies.set("deviceId", self.client_id, domain="mi.com")
        self.session.cookies.set("deviceId", self.client_id, domain="xiaomi.com")

    def _store_tokens(self, data: dict) -> None:
        self.user_id = str(data.get("userId") or self.user_id or "")
        self.ssecurity = data.get("ssecurity")
        self.c_user_id = data.get("cUserId")
        self.pass_token = data.get("passToken")

    def _fetch_service_token(self, location: str | None) -> None:
        if not location:
            return
        resp = self.session.get(
            location,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        self.service_token = resp.cookies.get("serviceToken") or self.service_token

    def login_password(
        self,
        username: str,
        password: str,
        country: str = "cn",
        captcha_handler=None,
        twofa_handler=None,
    ) -> bool:
        """密码登录。

        captcha_handler(image_bytes, captcha_url) -> str：返回验证码文本。
        twofa_handler(prompt) -> str：返回邮箱验证码文本。
        """
        self.username = username
        self.country = country
        self._init_login_cookies()

        headers = {
            "User-Agent": self.useragent,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        url = "https://account.xiaomi.com/pass/serviceLogin?sid=xiaomiio&_json=true"
        resp = self.session.get(url, headers=headers, cookies={"userId": username}, timeout=15)
        data = self._to_json(resp.text)
        if "ssecurity" in data:
            self._store_tokens(data)
            self._fetch_service_token(data.get("location"))
            self.save()
            return True
        sign = data.get("_sign")
        if not sign:
            raise MiCloudException(f"获取登录签名失败：{json.dumps(data, ensure_ascii=False)[:300]}")

        fields = {
            "sid": "xiaomiio",
            "hash": hashlib.md5(password.encode("utf-8")).hexdigest().upper(),
            "callback": "https://sts.api.io.mi.com/sts",
            "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "user": username,
            "_sign": sign,
            "_json": "true",
        }

        data = self._post_auth2(fields, headers)
        if "captchaUrl" in data and data.get("captchaUrl"):
            if captcha_handler is None:
                raise MiCloudException("小米要求图形验证码，请传入 captcha_handler")
            captcha_url = data["captchaUrl"]
            if captcha_url.startswith("/"):
                captcha_url = "https://account.xiaomi.com" + captcha_url
            image = self.session.get(captcha_url, timeout=15).content
            code = captcha_handler(image, captcha_url)
            if not code:
                raise MiCloudException("未输入验证码")
            fields["captCode"] = code
            data = self._post_auth2(fields, headers)
            if data.get("code") == 87001:
                raise MiCloudException("验证码错误")

        if "ssecurity" in data and len(str(data.get("ssecurity", ""))) > 4:
            self._store_tokens(data)
            self._fetch_service_token(data.get("location"))
            self.save()
            return True

        if "notificationUrl" in data:
            if twofa_handler is None:
                raise MiCloudException("小米要求两步验证，请传入 twofa_handler")
            self._do_2fa(data["notificationUrl"], twofa_handler)
            self.save()
            return True

        raise MiCloudException(f"登录失败：{json.dumps(data, ensure_ascii=False)[:400]}")

    def _post_auth2(self, fields: dict, headers: dict) -> dict:
        resp = self.session.post(
            "https://account.xiaomi.com/pass/serviceLoginAuth2",
            headers=headers,
            params=fields,
            allow_redirects=False,
            timeout=15,
        )
        return self._to_json(resp.text)

    def _do_2fa(self, notification_url: str, twofa_handler) -> None:
        headers = {
            "User-Agent": self.useragent,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        self.session.get(notification_url, headers=headers, timeout=15)

        query = parse_qs(urlparse(notification_url).query)
        context = query.get("context", [""])[0]
        list_params = {"sid": "xiaomiio", "context": context, "_locale": "zh_CN"}
        self.session.get(
            "https://account.xiaomi.com/identity/list",
            params=list_params,
            headers=headers,
            timeout=15,
        )

        send_params = {
            "_dc": str(int(time.time() * 1000)),
            "sid": "xiaomiio",
            "context": context,
            "mask": "0",
            "_locale": "zh_CN",
        }
        send_data = {
            "retry": "0",
            "icode": "",
            "_json": "true",
            "ick": self.session.cookies.get("ick", ""),
        }
        self.session.post(
            "https://account.xiaomi.com/identity/auth/sendEmailTicket",
            params=send_params,
            data=send_data,
            headers=headers,
            timeout=15,
        )

        code = twofa_handler("请输入小米账号邮箱收到的验证码")
        verify_params = {
            "_flag": "8",
            "_json": "true",
            "sid": "xiaomiio",
            "context": context,
            "mask": "0",
            "_locale": "zh_CN",
        }
        verify_data = {
            "_flag": "8",
            "ticket": str(code),
            "trust": "false",
            "_json": "true",
            "ick": self.session.cookies.get("ick", ""),
        }
        r = self.session.post(
            "https://account.xiaomi.com/identity/auth/verifyEmail",
            params=verify_params,
            data=verify_data,
            headers=headers,
            timeout=15,
        )

        finish_loc = None
        try:
            finish_loc = r.json().get("location")
        except Exception:
            finish_loc = r.headers.get("Location")

        if not finish_loc:
            m = re.search(r'https://account\.xiaomi\.com/identity/result/check\?[^"\']+', r.text)
            if m:
                finish_loc = m.group(0)

        if not finish_loc:
            r0 = self.session.get(
                "https://account.xiaomi.com/identity/result/check",
                params={"sid": "xiaomiio", "context": context, "_locale": "zh_CN"},
                headers=headers,
                allow_redirects=False,
                timeout=15,
            )
            finish_loc = r0.headers.get("Location")

        if not finish_loc:
            raise MiCloudException("无法取得两步验证完成地址")

        if "identity/result/check" in finish_loc:
            r = self.session.get(finish_loc, headers=headers, allow_redirects=False, timeout=15)
            end_url = r.headers.get("Location") or finish_loc
        else:
            end_url = finish_loc

        r = self.session.get(end_url, headers=headers, allow_redirects=False, timeout=15)
        if r.status_code == 200 and "Xiaomi Account - Tips" in r.text:
            r = self.session.get(end_url, headers=headers, allow_redirects=False, timeout=15)

        ext_prag = r.headers.get("extension-pragma")
        if ext_prag:
            try:
                ep = json.loads(ext_prag)
                if ep.get("ssecurity"):
                    self.ssecurity = ep["ssecurity"]
            except (ValueError, TypeError):
                pass

        if not self.ssecurity:
            raise MiCloudException("两步验证完成后未取得 ssecurity")

        sts_url = r.headers.get("Location")
        if not sts_url:
            idx = r.text.find("https://sts.api.io.mi.com/sts")
            if idx != -1:
                sts_url = r.text[idx: idx + 300].split('"')[0]
        if not sts_url:
            raise MiCloudException("未取得 STS 跳转地址")

        self.session.get(sts_url, headers=headers, timeout=15)
        self.service_token = (
            self.session.cookies.get("serviceToken", domain=".sts.api.io.mi.com")
            or self.session.cookies.get("serviceToken")
        )

    def login_qr(self, country: str = "cn", on_qr=None, poll_interval: float = 3.0) -> bool:
        """扫码登录。on_qr(image_bytes, login_url) 用于展示二维码。"""
        self.country = country
        self._init_login_cookies()

        url = "https://account.xiaomi.com/longPolling/loginUrl"
        params = {
            "_qrsize": "480",
            "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "callback": "https://sts.api.io.mi.com/sts",
            "_hasLogo": "false",
            "sid": "xiaomiio",
            "serviceParam": "",
            "_locale": "zh_CN",
            "_dc": str(int(time.time() * 1000)),
        }
        resp = self.session.get(url, params=params, timeout=15)
        data = self._to_json(resp.text)
        qr_url = data.get("qr")
        login_url = data.get("loginUrl")
        lp = data.get("lp")
        if not (qr_url and lp):
            raise MiCloudException(f"获取登录二维码失败：{json.dumps(data, ensure_ascii=False)[:300]}")

        image = self.session.get(qr_url, timeout=15).content
        if on_qr:
            on_qr(image, login_url)

        deadline = time.time() + int(data.get("timeout", 180))
        while time.time() < deadline:
            try:
                r = self.session.get(lp, timeout=10)
            except requests.exceptions.Timeout:
                continue
            except requests.exceptions.RequestException:
                time.sleep(poll_interval)
                continue
            if r.status_code != 200:
                time.sleep(poll_interval)
                continue
            try:
                scanned = self._to_json(r.text)
            except (ValueError, TypeError):
                time.sleep(poll_interval)
                continue
            if scanned.get("ssecurity"):
                self._store_tokens(scanned)
                self._fetch_service_token(scanned.get("location"))
                self.username = self.user_id or self.username
                self.save()
                return True
            time.sleep(poll_interval)

        raise MiCloudException("二维码已过期或未在有效期内扫码确认")

    # ------------------------------------------------------------------
    # MIoT 加密请求
    # ------------------------------------------------------------------
    @staticmethod
    def _to_json(text: str) -> dict:
        return json.loads(text.replace("&&&START&&&", ""))

    def _api_url(self, api: str) -> str:
        api = api.lstrip("/")
        if self.country == "cn":
            return f"https://api.io.mi.com/app/{api}"
        return f"https://{self.country}.api.io.mi.com/app/{api}"

    def _gen_nonce(self) -> str:
        millis = int(round(time.time() * 1000))
        b = (random.getrandbits(64) - 2**63).to_bytes(8, "big", signed=True)
        part2 = int(millis / 60000)
        b += part2.to_bytes(((part2.bit_length() + 7) // 8), "big")
        return base64.b64encode(b).decode("utf-8")

    def _signed_nonce(self, nonce: str) -> str:
        m = hashlib.sha256()
        m.update(base64.b64decode(self.ssecurity.encode("utf-8")))
        m.update(base64.b64decode(nonce.encode("utf-8")))
        return base64.b64encode(m.digest()).decode("utf-8")

    @staticmethod
    def _sha1_sign(method: str, url: str, data: dict, signed_nonce: str) -> str:
        path = urlparse(url).path
        if path[:5] == "/app/":
            path = path[4:]
        arr = [method.upper(), path]
        for k, v in data.items():
            arr.append(f"{k}={v}")
        arr.append(signed_nonce)
        raw = hashlib.sha1("&".join(arr).encode("utf-8")).digest()
        return base64.b64encode(raw).decode("utf-8")

    @staticmethod
    def _encrypt_data(pwd: str, data: str) -> str:
        r = ARC4.new(base64.b64decode(pwd))
        r.encrypt(bytes(1024))
        return base64.b64encode(r.encrypt(data.encode("utf-8"))).decode("utf-8")

    @staticmethod
    def _decrypt_data(pwd: str, data: str) -> bytes:
        r = ARC4.new(base64.b64decode(pwd))
        r.encrypt(bytes(1024))
        return r.encrypt(base64.b64decode(data))

    def _rc4_params(self, method: str, url: str, params: dict) -> dict:
        nonce = self._gen_nonce()
        signed_nonce = self._signed_nonce(nonce)
        params["rc4_hash__"] = self._sha1_sign(method, url, params, signed_nonce)
        for k, v in params.items():
            params[k] = self._encrypt_data(signed_nonce, v)
        params.update(
            {
                "signature": self._sha1_sign(method, url, params, signed_nonce),
                "ssecurity": self.ssecurity,
                "_nonce": nonce,
            }
        )
        return params

    def request_miot(self, api: str, params: list, timeout: float = 12):
        """调用 api.io.mi.com 的 MIoT 接口，返回 result 字段。"""
        if not self.is_configured:
            raise MiCloudException("尚未登录小米云，缺少 serviceToken / userId / ssecurity")

        url = self._api_url(api)
        form = {"data": json.dumps({"params": params}, separators=(",", ":"))}
        headers = {
            "Accept-Encoding": "identity",
            "X-XIAOMI-PROTOCAL-FLAG-CLI": "PROTOCAL-HTTP2",
            "Content-Type": "application/x-www-form-urlencoded",
            "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
            "User-Agent": self.useragent,
        }
        cookies = {
            "userId": str(self.user_id),
            "yetAnotherServiceToken": self.service_token,
            "serviceToken": self.service_token,
            "locale": self.locale,
            "timezone": self.timezone,
            "is_daylight": str(time.daylight),
            "dst_offset": str(time.localtime().tm_isdst * 60 * 60 * 1000),
            "channel": "MI_APP_STORE",
        }

        enc_params = self._rc4_params("POST", url, form)
        resp = self.session.post(url, data=enc_params, headers=headers, cookies=cookies, timeout=timeout)
        if resp.status_code != 200:
            raise MiCloudException(f"小米云 HTTP {resp.status_code}：{resp.text[:200]}")

        text = resp.text
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            signed_nonce = self._signed_nonce(enc_params["_nonce"])
            text = self._decrypt_data(signed_nonce, text).decode("utf-8", errors="replace")
            payload = json.loads(text)

        if payload.get("code") not in (0, None):
            raise MiCloudException(
                f"小米云返回错误：code={payload.get('code')} message={payload.get('message')}"
            )
        return payload.get("result")

    def get_prop(self, did: str, siid: int, piid: int, timeout: float = 12):
        """读取单个属性，返回 value。"""
        result = self.request_miot(
            "miotspec/prop/get",
            [{"did": str(did), "siid": siid, "piid": piid}],
            timeout=timeout,
        )
        if isinstance(result, list) and result:
            return result[0].get("value")
        return result

    def set_prop(self, did: str, siid: int, piid: int, value, timeout: float = 12):
        """写入单个属性。"""
        return self.request_miot(
            "miotspec/prop/set",
            [{"did": str(did), "siid": siid, "piid": piid, "value": value}],
            timeout=timeout,
        )


def _build_cli():
    import argparse

    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="小米云登录 / MIoT 测试工具")
    parser.add_argument("action", choices=["qr", "password", "status"])
    parser.add_argument("--username", help="小米账号")
    parser.add_argument("--password", help="小米账号密码")
    parser.add_argument("--country", default="cn")
    parser.add_argument("--config", default=os.path.join(here, "mi_cloud.json"))
    parser.add_argument("--did", default="2028659099")
    parser.add_argument("--siid", type=int, default=2)
    parser.add_argument("--piid", type=int, default=1)
    return parser


if __name__ == "__main__":
    args = _build_cli().parse_args()
    cloud = MiCloud(args.config)

    if args.action == "qr":
        def on_qr(image, login_url):
            path = os.path.join(os.path.dirname(args.config), "mi_qr.png")
            with open(path, "wb") as fh:
                fh.write(image)
            print(f"QR_SAVED:{path}", flush=True)
            print(f"LOGIN_URL:{login_url}", flush=True)

        cloud.login_qr(args.country, on_qr=on_qr)
        print("LOGIN_OK", flush=True)

    elif args.action == "password":
        def captcha_handler(image, captcha_url):
            path = os.path.join(os.path.dirname(args.config), "mi_captcha.png")
            with open(path, "wb") as fh:
                fh.write(image)
            print(f"CAPTCHA_SAVED:{path}", flush=True)
            print(f"CAPTCHA_URL:{captcha_url}", flush=True)
            return input("请输入验证码：").strip()

        def twofa_handler(prompt):
            print(prompt, flush=True)
            return input("验证码：").strip()

        username = args.username or input("小米账号：").strip()
        password = args.password or input("密码：").strip()
        cloud.login_password(
            username,
            password,
            args.country,
            captcha_handler=captcha_handler,
            twofa_handler=twofa_handler,
        )
        print("LOGIN_OK", flush=True)

    if args.action in ("qr", "password"):
        try:
            value = cloud.get_prop(args.did, args.siid, args.piid)
            print(f"STATUS_OK value={value!r}", flush=True)
        except MiCloudException as exc:
            print(f"STATUS_FAIL {exc}", flush=True)

    if args.action == "status":
        value = cloud.get_prop(args.did, args.siid, args.piid)
        print(f"STATUS_OK value={value!r}", flush=True)
