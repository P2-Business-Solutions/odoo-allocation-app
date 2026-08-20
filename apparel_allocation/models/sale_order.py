from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = "sale.order"

    allocation_state = fields.Selection(
        [
            ("pending", "Needs Allocation"),
            ("ready", "Allocation Ready"),
        ],
        string="Rule Status",
        compute="_compute_allocation_state",
        store=True,
        readonly=True,
        help="Whether the order satisfies the apparel allocation rules "
             "(size runs, minimum quantities, fill rates).",
    )
    allocation_message = fields.Text(
        string="Allocation Notes",
        compute="_compute_allocation_state",
        store=True,
        readonly=True,
    )
    allocation_ids = fields.One2many(
        "apparel.allocation",
        "sale_order_id",
        string="Allocations",
    )
    allocation_count = fields.Integer(
        string="Allocation Count",
        compute="_compute_allocation_count",
    )
    allocation_coverage = fields.Selection(
        [
            ("none", "Not Allocated"),
            ("partial", "Partially Allocated"),
            ("full", "Fully Allocated"),
        ],
        string="Allocation Coverage",
        compute="_compute_allocation_coverage",
        store=True,
    )
    allocation_pct = fields.Float(
        string="Allocated (%)",
        compute="_compute_allocation_coverage",
        store=True,
        aggregator="avg",
    )
    allocation_priority = fields.Selection(
        [
            ("0", "Normal"),
            ("1", "High"),
            ("2", "Critical"),
        ],
        string="Allocation Priority",
        default="0",
        index=True,
        help="Used by the bulk allocation wizard to decide which orders are "
             "served first when supply is scarce.",
    )

    # ------------------------------------------------------------------
    # Rule checks (order composition: size runs, fill rates, ...)
    # ------------------------------------------------------------------
    def _get_applicable_allocation_rules(self):
        """Return allocation rules applicable to this order's company."""
        self.ensure_one()
        company = self.company_id or self.env.company
        return (
            self.env["apparel.allocation.rule"]
            .sudo()
            .search(
                [
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=", company.id),
                ]
            )
        )

    @api.depends(
        "order_line",
        "order_line.product_id",
        "order_line.product_uom_qty",
    )
    def _compute_allocation_state(self):
        for order in self:
            messages = []
            rules = order._get_applicable_allocation_rules()
            for rule in rules:
                try:
                    missing = rule.check_allocation(order)
                    if missing:
                        messages.extend(missing)
                except UserError as exc:
                    messages.append(str(exc.args[0] if exc.args else exc))

            order.allocation_state = "ready" if not messages else "pending"
            order.allocation_message = "\n".join(messages)

    def action_recheck_allocation(self):
        """Manually refresh the rule status (stock levels may have moved)."""
        self._compute_allocation_state()
        return True

    def _check_allocation_ready(self):
        for order in self:
            if order.allocation_state != "ready":
                msg = order.allocation_message or _(
                    "Allocation rules are not satisfied for this order."
                )
                raise UserError(msg)

    # ------------------------------------------------------------------
    # Allocation coverage (ledger)
    # ------------------------------------------------------------------
    def _compute_allocation_count(self):
        for order in self:
            order.allocation_count = len(
                order.sudo().allocation_ids.filtered(
                    lambda a: a.state != "cancelled"
                )
            )

    @api.depends(
        "order_line.product_uom_qty",
        "order_line.qty_delivered",
        "order_line.allocation_ids.qty",
        "order_line.allocation_ids.state",
    )
    def _compute_allocation_coverage(self):
        for order in self:
            lines = order.sudo().order_line.filtered(
                lambda sol: not sol.display_type
                and sol.product_id
                and sol.product_id.is_storable
            )
            demand = sum(lines.mapped("product_uom_qty"))
            if not demand:
                order.allocation_coverage = False
                order.allocation_pct = 0.0
                continue
            allocated = 0.0
            for sol in lines:
                line_alloc = sum(
                    sol.allocation_ids.filtered(
                        lambda a: a.state in ("allocated", "done")
                    ).mapped("qty")
                )
                allocated += min(line_alloc, sol.product_uom_qty)
            pct = allocated / demand * 100.0
            order.allocation_pct = pct
            if float_compare(allocated, 0.0, precision_digits=3) <= 0:
                order.allocation_coverage = "none"
            elif float_compare(allocated, demand, precision_digits=3) >= 0:
                order.allocation_coverage = "full"
            else:
                order.allocation_coverage = "partial"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_view_allocations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Allocations"),
            "res_model": "apparel.allocation",
            "view_mode": "list,form",
            "domain": [("sale_order_id", "=", self.id)],
            "context": {
                "default_sale_line_id": self.order_line[:1].id,
                "search_default_filter_allocated": 1,
            },
        }

    def action_run_allocation(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Allocate Orders"),
            "res_model": "apparel.allocation.run",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_ids": [(6, 0, self.ids)],
            },
        }

    def action_release_allocations(self):
        self.sudo().allocation_ids.action_release()
        return True

    def _auto_allocate(self):
        """Allocate orders using the configured defaults."""
        Allocation = self.env["apparel.allocation"].sudo()
        options = Allocation._get_config_options()
        for order in self:
            Allocation.allocate_sale_lines(order.sudo().order_line, **options)

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------
    def action_confirm(self):
        self._check_allocation_ready()
        res = super().action_confirm()
        auto = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("apparel_allocation.auto_allocate_on_confirm")
        )
        if auto and str(auto).strip().lower() in ("true", "1", "yes"):
            self._auto_allocate()
        return res

    def _action_cancel(self):
        res = super()._action_cancel()
        self.sudo().allocation_ids.action_release()
        return res


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    allocation_ids = fields.One2many(
        "apparel.allocation",
        "sale_line_id",
        string="Allocations",
    )
    qty_allocated = fields.Float(
        string="Allocated Qty",
        compute="_compute_qty_allocated",
    )
    qty_to_allocate = fields.Float(
        string="Qty To Allocate",
        compute="_compute_qty_allocated",
    )

    @api.depends(
        "allocation_ids.qty",
        "allocation_ids.state",
        "product_uom_qty",
        "qty_delivered",
    )
    def _compute_qty_allocated(self):
        for sol in self:
            allocated = sum(
                sol.sudo().allocation_ids.filtered(
                    lambda a: a.state in ("allocated", "done")
                ).mapped("qty")
            )
            sol.qty_allocated = allocated
            if sol.display_type or not sol.product_id or not sol.product_id.is_storable:
                sol.qty_to_allocate = 0.0
            else:
                sol.qty_to_allocate = max(
                    sol.product_uom_qty - sol.qty_delivered - allocated, 0.0
                )
