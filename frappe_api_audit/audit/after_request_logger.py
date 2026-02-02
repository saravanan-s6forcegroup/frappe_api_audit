import frappe
import json

def is_external_api_call():
    headers = frappe.local.request.headers or {}
    form = frappe.form_dict or {}

    # 1️⃣ Authorization header (Bearer / Basic / Token)
    if headers.get("Authorization"):
        return True

    # 2️⃣ API key based auth (query or form)
    if form.get("api_key") and (form.get("api_secret") or form.get("api_token")):
        return True

    # 3️⃣ Explicit API client (no browser session)
    if not frappe.session.sid:
        return True

    return False


def log_api_request(response=None):
    # 🛑 recursion guard
    if getattr(frappe.local, "_api_audit_logging", False):
        return

    frappe.local._api_audit_logging = True

    try:
        # Ensure request
        if not hasattr(frappe.local, "request"):
            return

        path = frappe.local.request.path or ""

        # ONLY whitelisted API methods
        if not path.startswith("/api/method/"):
            return

        # 🔥 THIS IS THE KEY FILTER
        if not is_external_api_call():
            return

        # Extract method
        method = path.replace("/api/method/", "").strip()
        if not method:
            return

        # Load settings
        try:
            settings = frappe.get_single("API Audit Settings")
        except Exception:
            return

        if not settings.enabled:
            return

        user = frappe.session.user
        roles = frappe.get_roles(user)

        if user == "Guest" and not settings.log_guest:
            return

        if settings.allowed_roles:
            allowed = {r.role for r in settings.allowed_roles}
            if not allowed.intersection(roles):
                return

        # Status
        http_status = frappe.response.get("http_status_code", 200)
        status = "Success" if http_status < 400 else "Failed"

        # Payloads
        request_payload = dict(frappe.form_dict)
        response_data = frappe.response.get("message")

        resp_str = json.dumps(response_data, default=str) if response_data else ""
        preview = resp_str[: (settings.max_response_preview_kb or 4) * 1024]

        # Insert log
        frappe.get_doc({
            "doctype": "API Access Log",
            "method": method,
            "user": user,
            "ip_address": frappe.local.request_ip,
            "http_method": frappe.local.request.method,
            "status": status,
            "execution_time_ms": frappe.response.get("time_taken", 0),
            "response_size_bytes": len(resp_str),
            "request_payload": json.dumps(request_payload),
            "response_preview": preview,
            "error_trace": frappe.response.get("exc"),
            "app_name": method.split(".")[0],
            "role_snapshot": ", ".join(roles),
        }).insert(ignore_permissions=True)

        frappe.db.commit()

    finally:
        frappe.local._api_audit_logging = False
