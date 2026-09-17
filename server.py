import os
import json
import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import firebase_admin
from firebase_admin import credentials, db


# ==============================
# RIPON-BD LICENSE SERVER
# ==============================

APP_ID = "RIPON-BD"

DB_URL = "https://ripon-bd-default-rtdb.firebaseio.com"

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))


# ==============================
# FIREBASE SETUP
# ==============================

service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")

if not service_account_json:
    raise RuntimeError(
        "FIREBASE_SERVICE_ACCOUNT_JSON environment variable is missing."
    )

try:
    service_account_info = json.loads(service_account_json)

    cred = credentials.Certificate(service_account_info)

    firebase_admin.initialize_app(
        cred,
        {
            "databaseURL": DB_URL
        }
    )

    print("[✓] Firebase connected successfully")

except Exception as e:
    raise RuntimeError(f"Firebase initialization failed: {e}")


# ==============================
# HELPERS
# ==============================

def send_json(handler, status_code, data):
    response = json.dumps(data).encode("utf-8")

    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(response)))
    handler.end_headers()

    handler.wfile.write(response)


def valid_key_format(key):
    if not isinstance(key, str):
        return False

    # Example:
    # RIPON-ABCD-EFGH-IJKL
    parts = key.split("-")

    if len(parts) != 4:
        return False

    if parts[0] != "RIPON":
        return False

    if not all(len(x) == 4 for x in parts[1:]):
        return False

    return True


def check_expiry(expiry):
    if not expiry:
        return False

    if str(expiry).lower() == "lifetime":
        return True

    try:
        expiry_date = datetime.datetime.strptime(
            str(expiry),
            "%Y-%m-%d"
        ).date()

        return datetime.date.today() <= expiry_date

    except Exception:
        return False


# ==============================
# LICENSE CHECK
# ==============================

def check_license(data):

    key = str(data.get("key", "")).strip()
    app_id = str(data.get("app_id", "")).strip()
    hwid = str(data.get("hwid", "")).strip()

    if not key:
        return {
            "ok": False,
            "message": "License key required"
        }

    if app_id != APP_ID:
        return {
            "ok": False,
            "message": "Invalid application"
        }

    if not valid_key_format(key):
        return {
            "ok": False,
            "message": "Invalid key format"
        }

    if not hwid:
        return {
            "ok": False,
            "message": "HWID required"
        }

    try:
        ref = db.reference(f"keys/{key}")
        record = ref.get()

    except Exception as e:
        return {
            "ok": False,
            "message": "Database connection error"
        }

    if not record:
        return {
            "ok": False,
            "message": "License key not found"
        }

    if record.get("app_id") != APP_ID:
        return {
            "ok": False,
            "message": "License belongs to another application"
        }

    if record.get("approved") is not True:
        return {
            "ok": False,
            "message": "License is not approved"
        }

    if record.get("active") is not True:
        return {
            "ok": False,
            "message": "License is disabled"
        }

    expiry = record.get("expiry", "Lifetime")

    if not check_expiry(expiry):
        return {
            "ok": False,
            "message": "License expired"
        }

    # ==========================
    # HWID BINDING
    # ==========================

    saved_hwid = str(record.get("hwid", "")).strip()

    if saved_hwid:

        if saved_hwid != hwid:
            return {
                "ok": False,
                "message": "License already linked to another device"
            }

    else:

        # First successful device gets linked
        ref.update({
            "hwid": hwid
        })

    return {
        "ok": True,
        "message": "License approved",
        "name": record.get("name", "USER"),
        "expiry": expiry,
        "app_id": APP_ID
    }


# ==============================
# HTTP SERVER
# ==============================

class LicenseHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        print("[SERVER]", format % args)

    def do_GET(self):

        if self.path == "/health":

            send_json(
                self,
                200,
                {
                    "ok": True,
                    "status": "online",
                    "app_id": APP_ID
                }
            )

            return

        send_json(
            self,
            404,
            {
                "ok": False,
                "message": "Endpoint not found"
            }
        )

    def do_POST(self):

        if self.path != "/check-key":

            send_json(
                self,
                404,
                {
                    "ok": False,
                    "message": "Endpoint not found"
                }
            )

            return

        try:

            content_length = int(
                self.headers.get("Content-Length", 0)
            )

            body = self.rfile.read(content_length)

            data = json.loads(
                body.decode("utf-8")
            )

            result = check_license(data)

            if result.get("ok") is True:

                send_json(
                    self,
                    200,
                    result
                )

            else:

                send_json(
                    self,
                    403,
                    result
                )

        except json.JSONDecodeError:

            send_json(
                self,
                400,
                {
                    "ok": False,
                    "message": "Invalid JSON"
                }
            )

        except Exception as e:

            print("[ERROR]", e)

            send_json(
                self,
                500,
                {
                    "ok": False,
                    "message": "Server error"
                }
            )


# ==============================
# START SERVER
# ==============================

if __name__ == "__main__":

    print("=" * 45)
    print("        RIPON-BD LICENSE SERVER")
    print("=" * 45)
    print(f"APP ID : {APP_ID}")
    print(f"PORT   : {PORT}")
    print("STATUS : ONLINE")
    print("=" * 45)

    server = HTTPServer(
        (HOST, PORT),
        LicenseHandler
    )

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        print("\n[!] Server stopped")

    finally:
        server.server_close()