from odoo import api, fields, models, _


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    allocation_ids = fields.One2many(
        "apparel.allocation",
        "production_id",
        string="Allocations",
    )
    allocation_count = fields.Integer(
        string="Allocation Count",
        compute="_compute_allocation_count",
    )
    qty_allocated = fields.Float(
        string="Allocated Qty",
        compute="_compute_allocation_count",
    )
    qty_available_for_allocation = fields.Float(
        string="Available For Allocation",
        compute="_compute_allocation_count",
        help="Planned production quantity that has not been allocated to a "
             "sale order yet.",
    )

    @api.depends("allocation_ids.qty", "allocation_ids.state", "product_qty")
    def _compute_allocation_count(self):
        for production in self:
            active = production.sudo().allocation_ids.filtered(
                lambda a: a.state != "cancelled"
            )
            allocated = sum(
                active.filtered(lambda a: a.state == "allocated").mapped("qty")
            )
            production.allocation_count = len(active)
            production.qty_allocated = allocated
            production.qty_available_for_allocation = max(
                production.product_qty - allocated, 0.0
            )

    def action_view_allocations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Allocations"),
            "res_model": "apparel.allocation",
            "view_mode": "list,form",
            "domain": [("production_id", "=", self.id)],
            "context": {"search_default_filter_allocated": 1},
        }

    def action_cancel(self):
        res = super().action_cancel()
        self.sudo().allocation_ids.action_release()
        return res
