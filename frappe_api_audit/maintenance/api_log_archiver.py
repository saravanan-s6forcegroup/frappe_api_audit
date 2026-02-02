import frappe
import json
from frappe.utils import now_datetime, add_days

def archive_api_logs_to_s3():
    settings = frappe.get_single("API Audit Settings")
    if not settings.enabled:
        return

    # ----------------------------------
    # Date range: yesterday
    # ----------------------------------
    to_dt = now_datetime().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    from_dt = add_days(to_dt, -1)

    # ----------------------------------
    # Fetch logs
    # ----------------------------------
    logs = frappe.get_all(
        "API Access Log",
        filters={
            "creation": ["between", [from_dt, to_dt]]
        },
        fields="*"
    )

    if not logs:
        return

    # ----------------------------------
    # File name (dynamic)
    # ----------------------------------
    from_str = from_dt.strftime("%Y-%m-%d_%H-%M-%S")
    to_str = to_dt.strftime("%Y-%m-%d_%H-%M-%S")

    file_name = (
        f"staging_{from_str}_to_{to_str}_api_logs.jsonl"
    )

    # ----------------------------------
    # ✅ S3 prefix from settings
    # ----------------------------------
    s3_prefix = (settings.s3_prefix or "api_logs").strip("/")

    file_path = f"{s3_prefix}/{file_name}"

    # ----------------------------------
    # File content
    # ----------------------------------
    content = "\n".join(
        json.dumps(row, default=str) for row in logs
    )

    # ----------------------------------
    # Save to S3 via File doctype
    # ----------------------------------
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "content": content,
        "is_private": 1,
        "file_url": f"/private/files/{file_path}"
    })

    file_doc.insert(ignore_permissions=True)

    # ----------------------------------
    # Delete archived logs
    # ----------------------------------
    frappe.db.delete(
        "API Access Log",
        {
            "creation": ["between", [from_dt, to_dt]]
        }
    )

    frappe.db.commit()
