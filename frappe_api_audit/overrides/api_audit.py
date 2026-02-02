import frappe, json, time 
from functools import wraps 
from frappe import whitelist as original_whitelist 
 
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
 
def logging_whitelist(*args, **kwargs): 
    def decorator(fn): 
        wrapped = original_whitelist(*args, **kwargs)(fn) 
 
        @wraps(wrapped) 
        def wrapper(*a, **kw): 
            settings = get_settings() 
            if not settings.enabled: 
                return wrapped(*a, **kw) 
 
            user = frappe.session.user 
            roles = frappe.get_roles(user) 
 
            if user == "Guest" and not settings.log_guest: 
                return wrapped(*a, **kw) 
 
            if settings.allowed_roles: 
                allowed = {r.role for r in settings.allowed_roles} 
                if not allowed.intersection(roles): 
                    return wrapped(*a, **kw) 
 
            check_rate_limit(user, settings.rate_limit_per_minute) 
 
            start = time.perf_counter() 
            status = "Success" 
            response = None 
            error_trace = None 
 
            try: 
                response = wrapped(*a, **kw) 
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
 
                frappe.get_doc({ 
                    "doctype": "API Access Log", 
                    "method": f"{fn.__module__}.{fn.__name__}", 
                    "user": user, 
                    "ip_address": frappe.local.request_ip, 
                    "http_method": frappe.request.method if frappe.request else None, 
                    "status": status, 
                    "execution_time_ms": elapsed, 
                    "response_size_bytes": len(resp_str), 
                    "request_payload": json.dumps(masked), 
                    "response_preview": preview, 
                    "error_trace": error_trace, 
                    "app_name": fn.__module__.split(".")[0], 
                    "role_snapshot": ", ".join(roles), 
                }).insert(ignore_permissions=True) 
 
        return wrapper 
    return decorator 
 
frappe.whitelist = logging_whitelist 
 