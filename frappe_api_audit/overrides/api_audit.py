import frappe
import json
import time
from functools import wraps


RATE_BUCKET = {}


def get_settings():
    return frappe.get_single("API Audit Settings")


def mask_pii(data, fields):
    if not isinstance(data, dict):
        return data
    return {
        k: "***MASKED***" if k.lower() in fields else v
        for k, v in data.items()
    }


def check_rate_limit(user, limit):
    if not limit:
        return

    bucket = int(time.time() / 60)
    key = f"{user}:{bucket}"

    RATE_BUCKET[key] = RATE_BUCKET.get(key, 0) + 1
    if RATE_BUCKET[key] > limit:
        frappe.throw("Rate limit exceeded", frappe.PermissionError)


# ==================================================
# SAFE API-ONLY WHITELIST DECORATOR
# ==================================================
def api_audit_whitelist(*args, **kwargs):
    def decorator(fn):
        @frappe.whitelist(*args, **kwargs)
        @wraps(fn)
        def wrapper(*a, **kw):
            # Only API calls
            if not hasattr(frappe.local, "request"):
                return fn(*a, **kw)

            path = frappe.local.request.path or ""
            if not path.startswith("/api/"):
                return fn(*a, **kw)

            try:
                settings = get_settings()
            except Exception:
                return fn(*a, **kw)

            if not settings.enabled:
                return fn(*a, **kw)

            user = frappe.session.user
            roles = frappe.get_roles(user)

            if user == "Guest" and not settings.log_guest:
                return fn(*a, **kw)

            if settings.allowed_roles:
                allowed = {r.role for r in settings.allowed_roles}
                if not allowed.intersection(roles):
                    return fn(*a, **kw)

            rate_limit = getattr(settings, "rate_limit_per_inute_int", None)
            check_rate_limit(user, rate_limit)

            start = time.perf_counter()
            status = "Success"
            response = None
            error_trace = None

            try:
                response = fn(*a, **kw)
                return response
            except Exception:
                status = "Failed"
                error_trace = frappe.get_traceback()
                raise
            finally:
                elapsed = int((time.perf_counter() - start) * 1000)

                masked = mask_pii(
                    dict(frappe.form_dict),
                    set((settings.mask_fields or "").lower().split(","))
                )

                resp_str = json.dumps(response, default=str) if response else ""
                preview = resp_str[: (settings.max_response_preview_kb or 4) * 1024]

                try:
                    frappe.get_doc({
                        "doctype": "API Access Log",
                        "method": f"{fn.__module__}.{fn.__name__}",
                        "user": user,
                        "ip_address": frappe.local.request_ip,
                        "http_method": frappe.request.method,
                        "status": status,
                        "execution_time_ms": elapsed,
                        "response_size_bytes": len(resp_str),
                        "request_payload": json.dumps(masked),
                        "response_preview": preview,
                        "error_trace": error_trace,
                        "app_name": fn.__module__.split(".")[0],
                        "role_snapshot": ", ".join(roles),
                    }).insert(ignore_permissions=True)
                except Exception:
                    frappe.log_error(
                        frappe.get_traceback(),
                        "API Audit Log Insert Failed"
                    )

        return wrapper
    return decorator
