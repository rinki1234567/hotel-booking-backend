// Copyright (c) 2026, Frappe and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Seasonal Price", {
// 	refresh(frm) {

// 	},
// });
// seasonal_price.js file ke andar
frappe.ui.form.on('Seasonal Price', {
    after_save: function(frm) {
        // Aapka pura logic yahan aayega
        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Room Type',
                name: frm.doc.room_type
            },
            callback: function(r) {
                if(r.message) {
                    let room_type_doc = r.message;
                    let found = false;

                    if (!room_type_doc.pricing) {
                        room_type_doc.pricing = [];
                    }

                    $.each(room_type_doc.pricing, function(i, row) {
                        if(row.category === frm.doc.category) {
                            row.price = frm.doc.price;
                            found = true;
                        }
                    });

                    if(!found) {
                        // 'Room Pricing' Child Table ka naam hai, 'pricing' fieldname hai
                        let child = frappe.model.add_child(room_type_doc, 'Room Pricing', 'pricing');
                        child.category = frm.doc.category;
                        child.price = frm.doc.price;
                    }

                    frappe.call({
                        method: 'frappe.client.save',
                        args: { doc: room_type_doc },
                        callback: function() {
                            frappe.show_alert({
                                message:__('Room Type Pricing Table updated via VS Code!'), 
                                indicator:'green'
                            });
                        }
                    });
                }
            }
        });
    }
});