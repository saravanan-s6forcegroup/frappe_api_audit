import frappe 
from frappe.utils import now_datetime, add_to_date 
 
def alert_on_failure_spike(): 
    s = frappe.get_single("API Audit Settings") 
    if not s.enabled: 
        return 
 
    since = add_to_date( 
        now_datetime(), 
        minutes=-(s.failure_window_minutes or 5) 
    ) 
 
    count = frappe.db.count( 
        "API Access Log", 
        {"status": "Failed", "creation": (">=", since)} 
    ) 
 
    if count < (s.failure_threshold or 10): 
        return 
 
    last = frappe.cache().get_value("api_last_alert") 
    if last and (now_datetime() - last).seconds < (s.alert_cooldown_minutes or 30) * 60: 
        return 
 
    frappe.cache().set_value("api_last_alert", now_datetime()) 
 
    frappe.sendmail( 
        recipients=(s.alert_emails or "").split(","), 
        subject="🚨 API Failure Spike Detected", 
        message=f"{count} failures detected in last {s.failure_window_minutes} minutes" 
    ) 
 