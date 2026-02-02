// Copyright (c) 2026, 6fe and contributors
// For license information, please see license.txt

// frappe.ui.form.on("API Audit Settings", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on("API Audit Settings", {
    refresh(frm) {
        frm.add_custom_button("Archive API Logs Now", () => {
            frappe.call({
                method: "frappe_api_audit.maintenance.api_log_archiver.run_api_log_archival_now",
                callback: r => {
                    frappe.msgprint(r.message.message);
                }
            });
        });
    }
});
