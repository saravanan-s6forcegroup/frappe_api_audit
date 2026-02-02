import frappe
import json
from frappe.utils import now_datetime, add_to_date

def archive_api_logs_to_s3():
    settings = frappe.get_single("API Audit Settings")
    if not settings.enabled:
        return

    cutoff = add_to_date(
        now_datetime(),
        days=-(settings.retain_logs_days or 30)
    )

    logs = frappe.get_all(
        "API Access Log",
        filters={
            "creation": ("<", cutoff),
            "archived": 0
        },
        limit=settings.archive_batch_size or 5000,
        order_by="creation asc"
    )

    if not logs:
        return

    names = [l.name for l in logs]

    rows = frappe.get_all(
        "API Access Log",
        filters={"name": ("in", names)},
        fields="*"
    )

    content = "\n".join(json.dumps(r, default=str) for r in rows)

    from_ts = rows[0]["creation"].strftime("%Y%m%d_%H%M%S")
    to_ts = rows[-1]["creation"].strftime("%Y%m%d_%H%M%S")

    s3_path = (
        f"{settings.s3_prefix or 'api-logs'}/"
        f"staging_{from_ts}_to_{to_ts}_api_logs.jsonl"
    )

    # -------------------------------
    # Upload via File → S3
    # -------------------------------
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": s3_path.split("/")[-1],
        "content": content,
        "is_private": 1
    }).insert(ignore_permissions=True)

    # -------------------------------
    # Mark archived (optional)
    # -------------------------------
    frappe.db.set_value(
        "API Access Log",
        {"name": ("in", names)},
        {
            "archived": 1,
            "archive_file": file_doc.name
        }
    )

    # -------------------------------
    # 🔥 GUARANTEED DELETE
    # -------------------------------
    frappe.db.delete(
        "API Access Log",
        {"name": ("in", names)}
    )

    frappe.db.commit()
