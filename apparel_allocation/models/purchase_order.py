from odoo import api, fields, models, _


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    allocation_ids = fields.One2many(
        "apparel.allocation",
        "purchase_order_id",
        string="Allocations",
    )
    allocation_count = fields.Integer(
        string="Allocation Count",
        compute="_compute_allocation_count",
    )

    def _compute_allocation_count(self):
        for order in self:
            order.allocation_count = len(
                order.sudo().allocation_ids.filtered(
                    lambda a: a.state != "cancelled"
                )
            )

    def action_view_allocations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Allocations"),
            "res_model": "apparel.allocation",
            "view_mode": "list,form",
            "domain": [("purchase_order_id", "=", self.id)],
            "context": {"search_default_filter_allocated": 1},
        }

    def button_cancel(self):
        res = super().button_cancel()
        self.sudo().allocation_ids.action_release()
        return res


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    allocation_ids = fields.One2many(
        "apparel.allocation",
        "purchase_line_id",
        string="Allocations",
    )
    qty_allocated = fields.Float(
        string="Allocated Qty",
        compute="_compute_qty_allocated",
    )
    qty_available_for_allocation = fields.Float(
        string="Available For Allocation",
        compute="_compute_qty_allocated",
        help="Quantity still to receive that has not been allocated to a "
             "sale order yet.",
    )

    @api.depends("allocation_ids.qty", "allocation_ids.state", "product_qty",
                 "qty_received")
    def _compute_qty_allocated(self):
        for line in self:
            allocated = sum(
                line.sudo().allocation_ids.filtered(
                    lambda a: a.state == "allocated"
                ).mapped("qty")
            )
            line.qty_allocated = allocated
            line.qty_available_for_allocation = max(
                line.product_qty - line.qty_received - allocated, 0.0
            )
