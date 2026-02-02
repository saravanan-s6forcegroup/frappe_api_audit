# frappe_api_audit/audit/before_request.py
import frappe, time

RATE_BUCKET = {}

def rate_limit():
    if not frappe.request or not frappe.request.path.startswith("/api/"):
        return

    user = frappe.session.user
    bucket = int(time.time() / 60)
    key = f"{user}:{bucket}"

    RATE_BUCKET[key] = RATE_BUCKET.get(key, 0) + 1
