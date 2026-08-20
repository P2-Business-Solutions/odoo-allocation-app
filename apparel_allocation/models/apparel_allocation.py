from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class ApparelAllocation(models.Model):
    _name = "apparel.allocation"
    _description = "Apparel Allocation"
    _order = "date_needed, date_expected, id"

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Sale Order Line",
        required=True,
        index=True,
        ondelete="cascade",
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sale Order",
        related="sale_line_id.order_id",
        store=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        related="sale_order_id.partner_id",
        store=True,
    )
    customer_type_id = fields.Many2one(
        "apparel.customer.type",
        string="Customer Type",
        related="partner_id.customer_type_id",
        store=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        index=True,
    )
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Product Template",
        related="product_id.product_tmpl_id",
        store=True,
    )
    qty = fields.Float(string="Allocated Qty", required=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse", index=True)
    source_type = fields.Selection(
        [
            ("stock", "On-Hand Stock"),
            ("purchase", "Purchase Order"),
            ("manufacture", "Manufacturing Order"),
        ],
        string="Source",
        required=True,
        default="stock",
        index=True,
    )
    purchase_line_id = fields.Many2one(
        "purchase.order.line",
        string="Purchase Order Line",
        index=True,
        ondelete="cascade",
    )
    purchase_order_id = fields.Many2one(
        "purchase.order",
        string="Purchase Order",
        related="purchase_line_id.order_id",
        store=True,
        index=True,
    )
    production_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order",
        index=True,
        ondelete="cascade",
    )
    date_expected = fields.Datetime(
        string="Expected Date",
        compute="_compute_date_expected",
        store=True,
        help="Date the allocated quantity is expected to become available. "
             "Empty for on-hand stock (available now).",
    )
    date_needed = fields.Datetime(
        string="Needed Date",
        related="sale_order_id.commitment_date",
        store=True,
        help="Delivery date promised to the customer (order commitment date).",
    )
    is_late = fields.Boolean(
        string="Late Source",
        compute="_compute_is_late",
        store=True,
        help="The supply source is expected after the date promised to the "
             "customer.",
    )
    days_late = fields.Integer(
        string="Days Late",
        compute="_compute_is_late",
        store=True,
    )
    state = fields.Selection(
        [
            ("allocated", "Allocated"),
            ("done", "Fulfilled"),
            ("cancelled", "Released"),
        ],
        string="Status",
        default="allocated",
        required=True,
        index=True,
        copy=False,
    )
    note = fields.Char(string="Note")

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends(
        "source_type",
        "purchase_line_id.date_planned",
        "production_id.date_finished",
        "production_id.date_start",
    )
    def _compute_date_expected(self):
        for alloc in self:
            if alloc.source_type == "purchase" and alloc.purchase_line_id:
                alloc.date_expected = alloc.purchase_line_id.date_planned
            elif alloc.source_type == "manufacture" and alloc.production_id:
                alloc.date_expected = (
                    alloc.production_id.date_finished
                    or alloc.production_id.date_start
                )
            else:
                alloc.date_expected = False

    @api.depends("date_expected", "date_needed")
    def _compute_is_late(self):
        for alloc in self:
            late = bool(
                alloc.date_expected
                and alloc.date_needed
                and alloc.date_expected > alloc.date_needed
            )
            alloc.is_late = late
            alloc.days_late = (
                (alloc.date_expected - alloc.date_needed).days if late else 0
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("apparel.allocation")
                    or _("New")
                )
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains("qty")
    def _check_qty(self):
        for alloc in self:
            rounding = alloc.product_id.uom_id.rounding or 0.001
            if float_compare(alloc.qty, 0.0, precision_rounding=rounding) <= 0:
                raise ValidationError(
                    _("Allocated quantity must be strictly positive.")
                )

    @api.constrains("source_type", "purchase_line_id", "production_id",
                    "product_id", "sale_line_id")
    def _check_source_consistency(self):
        for alloc in self:
            if alloc.sale_line_id and alloc.product_id != alloc.sale_line_id.product_id:
                raise ValidationError(
                    _("Allocation product must match the sale order line "
                      "product (%(alloc)s).") % {"alloc": alloc.display_name}
                )
            if alloc.source_type == "purchase":
                if not alloc.purchase_line_id:
                    raise ValidationError(
                        _("A purchase-sourced allocation requires a purchase "
                          "order line.")
                    )
                if alloc.purchase_line_id.product_id != alloc.product_id:
                    raise ValidationError(
                        _("The purchase order line product does not match the "
                          "allocated product (%(alloc)s).")
                        % {"alloc": alloc.display_name}
                    )
            elif alloc.source_type == "manufacture":
                if not alloc.production_id:
                    raise ValidationError(
                        _("A manufacturing-sourced allocation requires a "
                          "manufacturing order.")
                    )
                if alloc.production_id.product_id != alloc.product_id:
                    raise ValidationError(
                        _("The manufacturing order product does not match the "
                          "allocated product (%(alloc)s).")
                        % {"alloc": alloc.display_name}
                    )

    @api.constrains("qty", "purchase_line_id", "production_id", "state",
                    "source_type")
    def _check_source_capacity(self):
        for alloc in self.filtered(lambda a: a.state == "allocated"):
            rounding = alloc.product_id.uom_id.rounding or 0.001
            if alloc.source_type == "purchase" and alloc.purchase_line_id:
                pol = alloc.purchase_line_id
                capacity = pol.product_qty - pol.qty_received
                total = self._purchase_line_allocated_qty(pol)
                if float_compare(total, capacity, precision_rounding=rounding) > 0:
                    raise ValidationError(
                        _("Over-allocation of purchase order line %(po)s: "
                          "%(total)s allocated but only %(cap)s remaining to "
                          "receive.")
                        % {
                            "po": pol.order_id.display_name,
                            "total": total,
                            "cap": capacity,
                        }
                    )
            elif alloc.source_type == "manufacture" and alloc.production_id:
                mo = alloc.production_id
                capacity = mo.product_qty
                total = self._production_allocated_qty(mo)
                if float_compare(total, capacity, precision_rounding=rounding) > 0:
                    raise ValidationError(
                        _("Over-allocation of manufacturing order %(mo)s: "
                          "%(total)s allocated but the order only produces "
                          "%(cap)s.")
                        % {
                            "mo": mo.display_name,
                            "total": total,
                            "cap": capacity,
                        }
                    )

    # ------------------------------------------------------------------
    # Allocated-quantity helpers
    # ------------------------------------------------------------------
    @api.model
    def _sum_allocated(self, domain):
        groups = self.sudo()._read_group(
            domain + [("state", "=", "allocated")], [], ["qty:sum"]
        )
        return (groups and groups[0][0]) or 0.0

    @api.model
    def _stock_allocated_qty(self, product, warehouse):
        """Open stock-sourced allocation quantity for *product*.

        Partially delivered quantities are netted out per sale line: once
        units ship, ``free_qty`` already reflects them, so counting the full
        allocation again would double-subtract from availability.
        """
        domain = [
            ("source_type", "=", "stock"),
            ("product_id", "=", product.id),
            ("state", "=", "allocated"),
        ]
        if warehouse:
            domain.append(("warehouse_id", "=", warehouse.id))
        allocations = self.sudo().search(domain)
        total = 0.0
        for line in allocations.mapped("sale_line_id"):
            line_qty = sum(
                allocations.filtered(
                    lambda a, l=line: a.sale_line_id == l
                ).mapped("qty")
            )
            total += max(line_qty - line.qty_delivered, 0.0)
        return total

    @api.model
    def _purchase_line_allocated_qty(self, pol):
        return self._sum_allocated([("purchase_line_id", "=", pol.id)])

    @api.model
    def _production_allocated_qty(self, mo):
        return self._sum_allocated([("production_id", "=", mo.id)])

    # ------------------------------------------------------------------
    # Supply discovery
    # ------------------------------------------------------------------
    @api.model
    def _get_free_stock_qty(self, product, warehouse):
        """Free on-hand quantity net of existing soft allocations."""
        product = product.sudo()
        if warehouse:
            product = product.with_context(
                warehouse=warehouse.id, warehouse_id=warehouse.id
            )
        return product.free_qty - self._stock_allocated_qty(product, warehouse)

    @api.model
    def _get_purchase_supply(self, product, warehouse, company):
        """Open purchase supply as [{'type', 'record', 'qty', 'date'}]."""
        lines = self.env["purchase.order.line"].sudo().search(
            [
                ("product_id", "=", product.id),
                ("order_id.state", "in", ("purchase", "done")),
                ("company_id", "=", company.id),
            ]
        )
        rounding = product.uom_id.rounding or 0.001
        result = []
        for pol in lines:
            if warehouse and pol.order_id.picking_type_id.warehouse_id != warehouse:
                continue
            remaining = (
                pol.product_qty
                - pol.qty_received
                - self._purchase_line_allocated_qty(pol)
            )
            if float_compare(remaining, 0.0, precision_rounding=rounding) > 0:
                result.append(
                    {
                        "type": "purchase",
                        "record": pol,
                        "qty": remaining,
                        "date": pol.date_planned,
                    }
                )
        return result

    @api.model
    def _get_manufacture_supply(self, product, warehouse, company):
        """Open manufacturing supply as [{'type', 'record', 'qty', 'date'}]."""
        productions = self.env["mrp.production"].sudo().search(
            [
                ("product_id", "=", product.id),
                ("state", "in", ("confirmed", "progress", "to_close")),
                ("company_id", "=", company.id),
            ]
        )
        rounding = product.uom_id.rounding or 0.001
        result = []
        for mo in productions:
            if warehouse and mo.picking_type_id.warehouse_id != warehouse:
                continue
            remaining = mo.product_qty - self._production_allocated_qty(mo)
            if float_compare(remaining, 0.0, precision_rounding=rounding) > 0:
                result.append(
                    {
                        "type": "manufacture",
                        "record": mo,
                        "qty": remaining,
                        "date": mo.date_finished or mo.date_start,
                    }
                )
        return result

    # ------------------------------------------------------------------
    # Configuration defaults
    # ------------------------------------------------------------------
    @api.model
    def _get_config_options(self):
        get_param = self.env["ir.config_parameter"].sudo().get_param

        def as_bool(key, default):
            value = get_param(key)
            if value in (False, None, ""):
                return default
            return str(value).strip().lower() in ("true", "1", "yes")

        def as_int(key, default=0):
            try:
                return int(get_param(key) or default)
            except (TypeError, ValueError):
                return default

        return {
            "source_stock": True,
            "source_purchase": as_bool(
                "apparel_allocation.allocate_from_po", True
            ),
            "source_manufacture": as_bool(
                "apparel_allocation.allocate_from_mo", True
            ),
            "horizon_days": as_int(
                "apparel_allocation.default_incoming_days", 0
            ),
            "enforce_date_match": as_bool(
                "apparel_allocation.enforce_date_match", False
            ),
            "tolerance_days": as_int(
                "apparel_allocation.date_tolerance_days", 0
            ),
        }

    # ------------------------------------------------------------------
    # Allocation engine
    # ------------------------------------------------------------------
    @api.model
    def allocate_sale_lines(self, lines, source_stock=True, source_purchase=True,
                            source_manufacture=True, horizon_days=0,
                            enforce_date_match=False, tolerance_days=0,
                            hard_reserve=False):
        """Allocate open demand on *lines* against available supply.

        Supply is consumed in date order: on-hand stock first, then future
        sources (purchase order lines and manufacturing orders) sorted by
        expected availability date.

        :param horizon_days: only consider future supply expected within
            this many days (0 = no limit).
        :param enforce_date_match: when True and the order has a commitment
            date, skip future supply expected after the commitment date plus
            ``tolerance_days``.
        :param hard_reserve: after allocating, try to reserve stock on the
            related delivery pickings for stock-sourced allocations.
        :return: recordset of created allocations.
        """
        created = self.browse()
        now = fields.Datetime.now()
        horizon_limit = (
            now + timedelta(days=horizon_days) if horizon_days else False
        )
        for sol in lines:
            if sol.display_type or not sol.product_id or not sol.product_id.is_storable:
                continue
            if sol.order_id.state == "cancel":
                continue
            product = sol.product_id
            rounding = product.uom_id.rounding or 0.001
            demand = sol.product_uom_qty - sol.qty_delivered - sol.qty_allocated
            if float_compare(demand, 0.0, precision_rounding=rounding) <= 0:
                continue

            order = sol.order_id
            warehouse = order.warehouse_id
            need_limit = False
            if enforce_date_match and order.commitment_date:
                need_limit = order.commitment_date + timedelta(days=tolerance_days)

            sources = []
            if source_stock:
                free = self._get_free_stock_qty(product, warehouse)
                if float_compare(free, 0.0, precision_rounding=rounding) > 0:
                    sources.append(
                        {"type": "stock", "record": None, "qty": free, "date": False}
                    )
            if source_purchase:
                sources.extend(
                    self._get_purchase_supply(product, warehouse, order.company_id)
                )
            if source_manufacture:
                sources.extend(
                    self._get_manufacture_supply(product, warehouse, order.company_id)
                )

            # On-hand first, then earliest future supply.
            sources.sort(key=lambda s: (bool(s["date"]), s["date"] or now))

            for src in sources:
                if float_compare(demand, 0.0, precision_rounding=rounding) <= 0:
                    break
                if src["date"]:
                    if horizon_limit and src["date"] > horizon_limit:
                        continue
                    if need_limit and src["date"] > need_limit:
                        continue
                take = min(demand, src["qty"])
                vals = {
                    "sale_line_id": sol.id,
                    "product_id": product.id,
                    "qty": take,
                    "warehouse_id": warehouse.id if warehouse else False,
                    "source_type": src["type"],
                    "company_id": order.company_id.id,
                }
                if src["type"] == "purchase":
                    vals["purchase_line_id"] = src["record"].id
                elif src["type"] == "manufacture":
                    vals["production_id"] = src["record"].id
                created |= self.create(vals)
                demand -= take

        if hard_reserve:
            created._action_reserve_stock()
        return created

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_release(self):
        self.filtered(lambda a: a.state == "allocated").write(
            {"state": "cancelled"}
        )
        return True

    def action_mark_done(self):
        self.filtered(lambda a: a.state == "allocated").write({"state": "done"})
        return True

    def _action_reserve_stock(self):
        """Hard reservation: assign delivery pickings of stock allocations."""
        pickings = self.filtered(
            lambda a: a.source_type == "stock" and a.state == "allocated"
        ).mapped("sale_order_id.picking_ids").filtered(
            lambda p: p.state in ("confirmed", "waiting")
        )
        if pickings:
            pickings.action_assign()
        return True

    @api.model
    def _cron_mark_done(self):
        """Mark allocations done once their sale line is fully delivered."""
        allocations = self.search([("state", "=", "allocated")])
        to_close = allocations.filtered(
            lambda a: a.sale_line_id
            and float_compare(
                a.sale_line_id.qty_delivered,
                a.sale_line_id.product_uom_qty,
                precision_rounding=a.product_id.uom_id.rounding or 0.001,
            ) >= 0
        )
        to_close.write({"state": "done"})
