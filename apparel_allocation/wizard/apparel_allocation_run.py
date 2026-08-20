from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApparelAllocationRun(models.TransientModel):
    _name = "apparel.allocation.run"
    _description = "Run Apparel Allocation"

    order_ids = fields.Many2many(
        "sale.order",
        string="Orders",
        domain=[("state", "in", ("draft", "sent", "sale"))],
    )
    source_stock = fields.Boolean(string="From On-Hand Stock", default=True)
    source_purchase = fields.Boolean(string="From Purchase Orders", default=True)
    source_manufacture = fields.Boolean(
        string="From Manufacturing Orders", default=True
    )
    horizon_days = fields.Integer(
        string="Supply Horizon (days)",
        help="Only consider future supply expected within this many days. "
             "0 = no limit.",
    )
    enforce_date_match = fields.Boolean(
        string="Match Supply By Date",
        help="Only allocate future supply expected on or before each order's "
             "commitment date (plus the tolerance below). Orders without a "
             "commitment date accept any future supply.",
    )
    tolerance_days = fields.Integer(
        string="Date Tolerance (days)",
        help="Accept future supply expected up to this many days after the "
             "commitment date.",
    )
    release_existing = fields.Boolean(
        string="Re-Allocate (Release Existing First)",
        help="Release the selected orders' current allocations before "
             "running, so supply is redistributed from scratch in the chosen "
             "priority sequence.",
    )
    sort_by = fields.Selection(
        [
            ("commitment_date", "Commitment Date (earliest first)"),
            ("priority", "Allocation Priority"),
            ("date_order", "Order Date (oldest first)"),
        ],
        string="Allocate In Order Of",
        default="commitment_date",
        required=True,
    )
    hard_reserve = fields.Boolean(
        string="Reserve Stock (Hard)",
        help="After allocating, reserve stock on the delivery pickings of "
             "confirmed orders for on-hand allocations.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        options = self.env["apparel.allocation"]._get_config_options()
        defaults = {
            "source_purchase": options["source_purchase"],
            "source_manufacture": options["source_manufacture"],
            "horizon_days": options["horizon_days"],
            "enforce_date_match": options["enforce_date_match"],
            "tolerance_days": options["tolerance_days"],
        }
        for field_name, value in defaults.items():
            if field_name in fields_list:
                res[field_name] = value
        if (
            "order_ids" in fields_list
            and not res.get("order_ids")
            and self.env.context.get("active_model") == "sale.order"
            and self.env.context.get("active_ids")
        ):
            res["order_ids"] = [(6, 0, self.env.context["active_ids"])]
        return res

    def _sorted_orders(self):
        self.ensure_one()
        far_future = fields.Datetime.now().replace(year=9999)
        if self.sort_by == "commitment_date":
            key = lambda o: (o.commitment_date or far_future, o.date_order or far_future)
        elif self.sort_by == "priority":
            key = lambda o: (
                -int(o.allocation_priority or "0"),
                o.commitment_date or far_future,
                o.date_order or far_future,
            )
        else:
            key = lambda o: o.date_order or far_future
        return self.order_ids.sorted(key=key)

    def action_run(self):
        self.ensure_one()
        if not self.order_ids:
            raise UserError(_("Select at least one order to allocate."))
        if not (self.source_stock or self.source_purchase or self.source_manufacture):
            raise UserError(_("Enable at least one supply source."))

        orders = self._sorted_orders()
        Allocation = self.env["apparel.allocation"]

        if self.release_existing:
            orders.mapped("allocation_ids").action_release()

        created = Allocation.browse()
        for order in orders:
            created |= Allocation.allocate_sale_lines(
                order.order_line,
                source_stock=self.source_stock,
                source_purchase=self.source_purchase,
                source_manufacture=self.source_manufacture,
                horizon_days=self.horizon_days,
                enforce_date_match=self.enforce_date_match,
                tolerance_days=self.tolerance_days,
            )
        if self.hard_reserve:
            created._action_reserve_stock()

        if not created:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Allocation"),
                    "message": _(
                        "No new allocations were created. Demand may already "
                        "be covered, or no matching supply was found within "
                        "the date constraints."
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Created Allocations"),
            "res_model": "apparel.allocation",
            "view_mode": "list,form",
            "domain": [("id", "in", created.ids)],
        }
