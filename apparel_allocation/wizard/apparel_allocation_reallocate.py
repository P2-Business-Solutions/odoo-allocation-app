from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApparelAllocationReallocate(models.TransientModel):
    _name = "apparel.allocation.reallocate"
    _description = "Reallocate Apparel Allocations"

    allocation_ids = fields.Many2many(
        "apparel.allocation",
        string="Allocations",
        domain=[("state", "=", "allocated")],
    )
    mode = fields.Selection(
        [
            ("release", "Release (free the supply)"),
            ("change_source", "Move To Another Source"),
        ],
        string="Action",
        default="release",
        required=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        compute="_compute_product_id",
        help="Set when all selected allocations share a single product; "
             "required to move allocations to a specific PO or MO.",
    )
    new_source_type = fields.Selection(
        [
            ("stock", "On-Hand Stock"),
            ("purchase", "Purchase Order"),
            ("manufacture", "Manufacturing Order"),
        ],
        string="New Source",
        default="stock",
    )
    new_purchase_line_id = fields.Many2one(
        "purchase.order.line",
        string="New Purchase Order Line",
        domain="[('product_id', '=', product_id),"
               " ('order_id.state', 'in', ('purchase', 'done'))]",
    )
    new_production_id = fields.Many2one(
        "mrp.production",
        string="New Manufacturing Order",
        domain="[('product_id', '=', product_id),"
               " ('state', 'in', ('confirmed', 'progress', 'to_close'))]",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if (
            "allocation_ids" in fields_list
            and not res.get("allocation_ids")
            and self.env.context.get("active_model") == "apparel.allocation"
            and self.env.context.get("active_ids")
        ):
            res["allocation_ids"] = [(6, 0, self.env.context["active_ids"])]
        return res

    @api.depends("allocation_ids")
    def _compute_product_id(self):
        for wizard in self:
            products = wizard.allocation_ids.mapped("product_id")
            wizard.product_id = products if len(products) == 1 else False

    def action_apply(self):
        self.ensure_one()
        allocations = self.allocation_ids.filtered(
            lambda a: a.state == "allocated"
        )
        if not allocations:
            raise UserError(_("Select at least one active allocation."))

        if self.mode == "release":
            allocations.action_release()
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Allocations Released"),
                    "message": _(
                        "%(count)s allocation(s) released. The supply is "
                        "available for re-allocation."
                    ) % {"count": len(allocations)},
                    "type": "success",
                    "sticky": False,
                },
            }

        # --- change source -------------------------------------------
        if self.new_source_type == "purchase" and not self.new_purchase_line_id:
            raise UserError(_("Select the destination purchase order line."))
        if self.new_source_type == "manufacture" and not self.new_production_id:
            raise UserError(_("Select the destination manufacturing order."))
        if self.new_source_type in ("purchase", "manufacture") and not self.product_id:
            raise UserError(
                _("Moving allocations to a specific PO or MO requires all "
                  "selected allocations to share the same product.")
            )

        Allocation = self.env["apparel.allocation"]
        new_allocations = Allocation.browse()
        for alloc in allocations:
            vals = {
                "sale_line_id": alloc.sale_line_id.id,
                "product_id": alloc.product_id.id,
                "qty": alloc.qty,
                "warehouse_id": alloc.warehouse_id.id,
                "company_id": alloc.company_id.id,
                "source_type": self.new_source_type,
                "purchase_line_id": (
                    self.new_purchase_line_id.id
                    if self.new_source_type == "purchase"
                    else False
                ),
                "production_id": (
                    self.new_production_id.id
                    if self.new_source_type == "manufacture"
                    else False
                ),
                "note": _("Reallocated from %(name)s") % {"name": alloc.name},
            }
            alloc.write({"state": "cancelled"})
            new_alloc = Allocation.create(vals)
            alloc.note = _("Moved to %(name)s") % {"name": new_alloc.name}
            new_allocations |= new_alloc

        return {
            "type": "ir.actions.act_window",
            "name": _("Reallocated"),
            "res_model": "apparel.allocation",
            "view_mode": "list,form",
            "domain": [("id", "in", new_allocations.ids)],
        }
