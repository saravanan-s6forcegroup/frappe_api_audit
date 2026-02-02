import frappe
import json

ARCHIVE_FIELDS = [
    "name",
    "creation",
    "method",
    "user",
    "ip_address",
    "http_method",
    "status",
    "execution_time_ms",
    "response_size_bytes",
    "request_payload",
    "response_preview",
    "error_trace",
    "app_name",
    "role_snapshot",
]

def archive_api_logs_dynamic_range():
    settings = frappe.get_single("API Audit Settings")

    if not settings.enabled:
        frappe.throw("API Audit is disabled")

    # ----------------------------------
    # Fetch ONLY required fields
    # ----------------------------------
    logs = frappe.get_all(
        "API Access Log",
        fields=["name", "creation"],
        order_by="creation asc"
    )

    if not logs:
        return {
            "status": "noop",
            "message": "No API logs found to archive"
        }

    names = [l["name"] for l in logs]

    rows = frappe.get_all(
        "API Access Log",
        filters={"name": ("in", names)},
        fields=ARCHIVE_FIELDS,
        order_by="creation asc"
    )

    # ----------------------------------
    # Actual time range
    # ----------------------------------
    from_dt = rows[0]["creation"]
    to_dt = rows[-1]["creation"]

    from_str = from_dt.strftime("%Y%m%d_%H%M%S")
    to_str = to_dt.strftime("%Y%m%d_%H%M%S")

    file_name = f"staging_{from_str}_to_{to_str}_api_logs.jsonl"

    s3_prefix = (settings.s3_prefix or "api_logs").strip("/")
    file_path = f"{s3_prefix}/{file_name}"

    # ----------------------------------
    # JSONL content
    # ----------------------------------
    content = "\n".join(
        json.dumps(row, default=str) for row in rows
    )

    # ----------------------------------
    # Upload to S3
    # ----------------------------------
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "content": content,
        "is_private": 1
    }).insert(ignore_permissions=True)

    # ----------------------------------
    # Delete archived logs
    # ----------------------------------
    frappe.db.delete(
        "API Access Log",
        {"name": ("in", names)}
    )

    frappe.db.commit()

    return {
        "status": "success",
        "message": f"{len(names)} API logs archived to S3",
        "from": from_dt,
        "to": to_dt,
        "file": file_doc.file_url
    }


@frappe.whitelist()
def run_api_log_archival_now():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Not permitted")

    return archive_api_logs_dynamic_range()
