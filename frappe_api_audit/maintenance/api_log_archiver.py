import frappe
import json
from frappe.utils import now_datetime, add_days

# ==========================================================
# CORE FUNCTION — MANUAL ARCHIVE (YESTERDAY)
# ==========================================================
def archive_api_logs_for_date_range(from_dt, to_dt):
    settings = frappe.get_single("API Audit Settings")

    if not settings.enabled:
        frappe.throw("API Audit is disabled")

    # ----------------------------------
    # Fetch logs in range
    # ----------------------------------
    logs = frappe.get_all(
        "API Access Log",
        filters={
            "creation": ["between", [from_dt, to_dt]]
        },
        fields="*",
        order_by="creation asc"
    )

    if not logs:
        return {
            "status": "noop",
            "message": "No API logs found for the selected period"
        }

    # ----------------------------------
    # File naming
    # ----------------------------------
    from_str = from_dt.strftime("%Y%m%d_%H%M%S")
    to_str = to_dt.strftime("%Y%m%d_%H%M%S")

    file_name = f"staging_{from_str}_to_{to_str}_api_logs.jsonl"

    s3_prefix = (settings.s3_prefix or "api_logs").strip("/")
    file_path = f"{s3_prefix}/{file_name}"

    # ----------------------------------
    # File content (JSONL)
    # ----------------------------------
    content = "\n".join(
        json.dumps(row, default=str) for row in logs
    )

    # ----------------------------------
    # Upload to S3 via File doctype
    # ----------------------------------
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "content": content,
        "is_private": 1
    }).insert(ignore_permissions=True)

    # ----------------------------------
    # DELETE LOGS (by primary key)
    # ----------------------------------
    names = [l["name"] for l in logs]

    frappe.db.delete(
        "API Access Log",
        {"name": ("in", names)}
    )

    frappe.db.commit()

    return {
        "status": "success",
        "message": f"{len(names)} API logs archived to S3",
        "file": file_doc.file_url
    }


# ==========================================================
# MANUAL API (BUTTON CALLS THIS)
# ==========================================================
@frappe.whitelist()
def run_api_log_archival_now():
    # 🔐 Security
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Not permitted")

    # ----------------------------------
    # Yesterday → Today (00:00)
    # ----------------------------------
    to_dt = now_datetime().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    from_dt = add_days(to_dt, -1)

    result = archive_api_logs_for_date_range(from_dt, to_dt)

    return result
