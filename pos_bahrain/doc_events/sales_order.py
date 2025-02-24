from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt, today
from erpnext.setup.utils import get_exchange_rate
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_delivery_note
from erpnext.stock.doctype.packed_item.packed_item import make_packing_list
from pos_bahrain.api.sales_invoice import get_customer_account_balance
from functools import partial
from toolz import first, compose, pluck, unique
from .sales_invoice import set_location

def validate(doc, method):

    custom_update_current_stock(doc)
		if doc.get('doctype') != "Sales Invoice":
				custom_after_save(doc, method)
				make_packing_list(doc)

def custom_update_current_stock(doc):
    if doc.get('packed_items'):
        for d in doc.get('packed_items'):
            bin = frappe.db.sql("SELECT actual_qty, projected_qty FROM `tabBin` WHERE item_code = %s AND warehouse = %s", 
                                (d.item_code, d.warehouse), as_dict=1)
            d.actual_qty = bin and flt(bin[0]['actual_qty']) or 0
            d.projected_qty = bin and flt(bin[0]['projected_qty']) or 0

            if not d.parent_item:
                linked_item = next((item.item_code for item in doc.items if item.item_code == d.item_code), None)
                d.parent_item = linked_item or doc.items[0].item_code

def custom_after_save(doc, method):
    if doc.is_new():
        make_packing_list(doc)
  

def make_packing_list(doc, update_existing=False):
    for item in doc.get("items", []):
        if item.prevdoc_docname: 
            quotation = frappe.get_doc("Quotation", item.prevdoc_docname)

            existing_packed_items = {d.item_code for d in doc.get("packed_items", [])}

            for packed_item in quotation.get("packed_items", []):
                if packed_item.item_code not in existing_packed_items or update_existing:
                    doc.append("packed_items", {
                        "parent_item": item.item_code,
                        "item_code": packed_item.item_code,
                        "item_name": packed_item.item_name,
                        "qty": packed_item.qty,
                        "description": packed_item.description,
                    })
                else:
                    for item in doc.get("items", []):
                        if not any(d.parent_item == item.item_code for d in doc.get("packed_items", [])):
                            make_packing_list(doc)

def before_save(doc, method):
    set_location(doc)

def on_submit(doc, method):
    update_against_quotation(doc)
    custom_after_save(doc, method)
    make_packing_list(doc)

def before_cancel(doc, method):
    update_quotation_sales_order(doc)

@frappe.whitelist()
def update_against_quotation(doc):
    get_qns = compose(
        list,
        unique,
        partial(pluck, "prevdoc_docname"),
        frappe.db.sql,
    )
    
    qns = get_qns(
        """
            Select prevdoc_docname From `tabSales Order Item` where docstatus = 1 AND parent=%(so)s
        """,
        values={"so": doc.name},
        as_dict=1,
    )
   
    if qns :
        for row in qns:
            
            frappe.db.sql("""
			update `tabQuotation` 
				set sales_order = "{sales_order}"
				where docstatus=1 AND name="{quotation}";""".format( sales_order= doc.name,quotation=row))
            frappe.db.commit()
@frappe.whitelist()
def update_quotation_sales_order(doc):
    get_qns = compose(
        list,
        unique,
        partial(pluck, "prevdoc_docname"),
        frappe.db.sql,
    )
    
    qns = get_qns(
        """
            Select prevdoc_docname From `tabSales Order Item` where docstatus = 1 AND parent=%(so)s
        """,
        values={"so": doc.name},
        as_dict=1,
    )
   
    if qns :
        for row in qns:
            
            frappe.db.sql("""
			update `tabQuotation` 
				set sales_order = ""
				where docstatus=1 AND name="{quotation}";""".format( quotation=row))
            frappe.db.commit()
