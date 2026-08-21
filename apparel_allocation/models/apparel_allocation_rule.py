from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ApparelAllocationRule(models.Model):
    _name = "apparel.allocation.rule"
    _description = "Apparel Allocation Rule"
    _order = "sequence, id"

    # ------------------------------------------------------------------
    # General
    # ------------------------------------------------------------------
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    notes = fields.Html(string="Internal Notes")

    # ------------------------------------------------------------------
    # Eligibility — which orders / partners does this rule apply to?
    # ------------------------------------------------------------------
    partner_tag_ids = fields.Many2many(
        "res.partner.category",
        string="Customer Tags",
        help="If set, this rule only applies to orders whose customer carries "
             "at least one of these tags. Leave empty to apply to all customers.",
    )
    partner_customer_type_ids = fields.Many2many(
        "apparel.customer.type",
        string="Customer Types",
        help="If set, this rule only applies to orders whose customer has one "
             "of these customer types (e.g., Wholesale, Distributor). "
             "Leave empty to apply to all customers.",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Fallback Warehouse",
        help="When a sale order line has no explicit warehouse, this warehouse "
             "is used for availability lookups. Leave empty to use the order's "
             "warehouse.",
    )
    product_template_ids = fields.Many2many(
        "product.template",
        string="Product Templates",
        help="Product templates this rule applies to. Leave empty to apply "
             "to all storable / consumable products on matching orders.",
    )
    attribute_id = fields.Many2one(
        "product.attribute",
        string="Size Attribute",
        help="The product attribute that represents sizing (e.g., 'Size').",
    )

    # ------------------------------------------------------------------
    # Criteria — what conditions must be met?
    # ------------------------------------------------------------------
    require_complete_size_run = fields.Boolean(
        string="Require Complete Size Run",
        help="When enabled, every size present on the order for a style/color "
             "must have at least 1 unit allocatable.",
    )
    min_fill_rate_style = fields.Float(
        string="Min Fill Rate per Style/Color (%)",
        digits=(5, 2),
        help="Minimum percentage of ordered quantity that must be allocatable "
             "for each style/color. 0 = no minimum.",
    )
    min_fill_rate_order = fields.Float(
        string="Min Fill Rate per Order (%)",
        digits=(5, 2),
        help="Minimum percentage of total ordered quantity across the entire "
             "order that must be allocatable. 0 = no minimum.",
    )
    include_incoming_days = fields.Integer(
        string="Include Incoming Stock (days)",
        default=0,
        help="Include expected incoming stock within N days when computing "
             "availability. 0 = only consider on-hand stock.",
    )
    use_variants = fields.Boolean(
        string="Use Product Variants",
        help="Override the global setting for this rule. When enabled, "
             "allocation evaluates individual product variants (sizes).",
    )
    allow_partial = fields.Boolean(
        string="Allow Partial Allocation",
        help="When enabled, the order can proceed even when some allocation "
             "targets are not fully met. Unmet targets are logged as warnings.",
    )

    # ------------------------------------------------------------------
    # Engine targets — how should allocation runs fill eligible orders?
    # ------------------------------------------------------------------
    engine_enabled = fields.Boolean(
        string="Drive Allocation Runs",
        help="When enabled, allocation runs apply this rule's fill target to "
             "eligible orders: each order (or each style/color group) is "
             "either filled to at least the target percentage or left "
             "untouched, so supply is never dribbled away on orders that "
             "cannot ship.",
    )
    engine_fill_level = fields.Selection(
        [
            ("line", "Each Style / Color"),
            ("order", "Entire Order"),
        ],
        string="Fill Target Applies To",
        default="line",
        required=True,
        help="Each Style / Color: the target is checked per product "
             "template + color combination (a size run).\n"
             "Entire Order: the target is checked once across all of the "
             "order's products.",
    )
    engine_fill_target = fields.Float(
        string="Target Fill Rate (%)",
        digits=(5, 2),
        default=100.0,
        help="Minimum achievable fill percentage required before anything is "
             "allocated to the group. 100 = only allocate complete groups.",
    )
    engine_size_run_aware = fields.Boolean(
        string="Balanced Size Runs",
        default=True,
        help="Allocate every size at the same rate, so partially filled "
             "groups keep a complete, proportional size run instead of some "
             "sizes being filled 100% while others get nothing.",
    )
    color_attribute_id = fields.Many2one(
        "product.attribute",
        string="Color Attribute",
        help="Attribute that represents color (e.g. 'Color'). Used to split "
             "order lines into style/color groups. Leave empty to group by "
             "product template only.",
    )

    @api.constrains("engine_enabled", "engine_fill_target")
    def _check_engine_fill_target(self):
        for rule in self:
            if rule.engine_enabled and not (0.0 < rule.engine_fill_target <= 100.0):
                raise ValidationError(
                    _("The target fill rate must be greater than 0 and at "
                      "most 100%.")
                )

    def _group_lines_for_engine(self, lines):
        """Split *lines* into engine allocation groups.

        Returns a list of ``(label, lines)`` tuples: one group for the whole
        order when the fill level is 'order', otherwise one group per product
        template + color value (each group representing one size run — the
        sizes are simply the product variants inside the group, so no size
        enumeration is needed).
        """
        self.ensure_one()
        storable = lines.filtered(
            lambda sol: not sol.display_type
            and sol.product_id
            and sol.product_id.is_storable
        )
        if not storable:
            return []
        if self.engine_fill_level == "order":
            return [(_("Entire order"), storable)]
        groups = {}
        for sol in storable:
            color = self.env["product.template.attribute.value"]
            if self.color_attribute_id:
                color = sol.product_id.product_template_attribute_value_ids.filtered(
                    lambda ptav: ptav.attribute_id == self.color_attribute_id
                )[:1]
            key = (sol.product_id.product_tmpl_id.id, color.id)
            if key not in groups:
                label = sol.product_id.product_tmpl_id.display_name
                if color:
                    label = "%s (%s)" % (label, color.name)
                groups[key] = (label, self.env["sale.order.line"])
            label, group = groups[key]
            groups[key] = (label, group | sol)
        return list(groups.values())

    # ------------------------------------------------------------------
    # Reservation mode
    # ------------------------------------------------------------------
    reservation_mode = fields.Selection(
        [
            ("soft", "Soft (Ledger Only)"),
            ("hard", "Hard (Reserve Stock)"),
        ],
        string="Reservation Mode",
        default="soft",
        required=True,
        help="Soft: creates a planning reservation in the allocation ledger "
             "without touching stock moves.\n"
             "Hard: reserves actual quants on stock moves.",
    )

    # ------------------------------------------------------------------
    # Size target lines
    # ------------------------------------------------------------------
    line_ids = fields.One2many(
        "apparel.allocation.rule.line",
        "rule_id",
        string="Size Targets",
        copy=True,
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _get_use_variants(self):
        param_value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("apparel_allocation.use_product_variants", default="False")
        )
        return param_value.lower() == "true"

    def is_variant_enabled(self):
        self.ensure_one()
        if self.use_variants:
            return True
        return self._get_use_variants()

    # ------------------------------------------------------------------
    # Eligibility check
    # ------------------------------------------------------------------
    def _is_eligible(self, order):
        """Return True if *order* matches this rule's eligibility filters."""
        self.ensure_one()
        partner = order.partner_id

        if self.partner_tag_ids:
            if not (partner.category_id & self.partner_tag_ids):
                return False

        if self.partner_customer_type_ids:
            partner_type = partner.customer_type_id if partner.customer_type_id else False
            if not partner_type or partner_type not in self.partner_customer_type_ids:
                return False

        return True

    def _get_eligible_templates(self, order):
        """Return product.template recordset that this rule covers on *order*."""
        self.ensure_one()
        order_templates = order.order_line.product_id.product_tmpl_id
        if self.product_template_ids:
            return order_templates & self.product_template_ids
        return order_templates

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------
    def _get_incoming_horizon(self):
        """Days of incoming-stock lookahead for this rule."""
        self.ensure_one()
        if self.include_incoming_days:
            return self.include_incoming_days
        param = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("apparel_allocation.default_incoming_days", "0")
        )
        try:
            return int(param or 0)
        except (TypeError, ValueError):
            return 0

    def _get_availability(self, products, warehouse, company):
        """Allocatable quantity for *products*: net free stock plus incoming
        supply (POs/MOs) within the rule's lookahead horizon."""
        self.ensure_one()
        Allocation = self.env["apparel.allocation"]
        horizon = self._get_incoming_horizon()
        limit = (
            fields.Datetime.now() + timedelta(days=horizon) if horizon > 0 else False
        )
        total = 0.0
        for product in products:
            if not product.is_storable:
                continue
            total += max(Allocation._get_free_stock_qty(product, warehouse), 0.0)
            if limit:
                supply = Allocation._get_purchase_supply(
                    product, warehouse, company
                ) + Allocation._get_manufacture_supply(product, warehouse, company)
                total += sum(
                    src["qty"]
                    for src in supply
                    if not src["date"] or src["date"] <= limit
                )
        return total

    # ------------------------------------------------------------------
    # Allocation check
    # ------------------------------------------------------------------
    def check_allocation(self, order):
        """Validate *order* against this rule.

        Returns a list of human-readable messages for unmet targets.
        Raises ``UserError`` when ``allow_partial`` is False and targets
        are not met.
        """
        self.ensure_one()

        if not self._is_eligible(order):
            return []

        templates = self._get_eligible_templates(order)
        if not templates:
            return []

        variant_mode = self.is_variant_enabled()
        all_missing = []

        for template in templates:
            template_lines = order.order_line.filtered(
                lambda sol: sol.product_id.product_tmpl_id == template
            )
            if not template_lines:
                continue

            missing = self._check_template_allocation(
                order, template, template_lines, variant_mode
            )
            all_missing.extend(missing)

        # --- Min fill rate per order ---------------------------------
        if self.min_fill_rate_order:
            storable_lines = order.order_line.filtered(
                lambda sol: not sol.display_type
                and sol.product_id
                and sol.product_id.is_storable
            )
            ordered_total = sum(storable_lines.mapped("product_uom_qty"))
            if ordered_total:
                warehouse = order.warehouse_id or self.warehouse_id
                available = self._get_availability(
                    storable_lines.mapped("product_id"),
                    warehouse,
                    order.company_id,
                )
                fill = min(available / ordered_total * 100.0, 100.0)
                if fill < self.min_fill_rate_order:
                    all_missing.append(
                        _("Order fill rate %(fill).1f%% is below the required "
                          "%(min).1f%%")
                        % {"fill": fill, "min": self.min_fill_rate_order}
                    )

        if all_missing and not self.allow_partial:
            raise UserError(
                _("Allocation rule '%(rule)s' not satisfied:\n%(details)s")
                % {"rule": self.display_name, "details": "\n".join(all_missing)}
            )
        return all_missing

    def _check_template_allocation(self, order, template, order_lines,
                                   variant_mode):
        """Check a single template against size-target lines and criteria.

        Returns list of missing-target messages.
        """
        self.ensure_one()
        missing = []

        # --- Size target lines -------------------------------------------
        if self.line_ids:
            for line in self.line_ids:
                required_qty = line.min_qty
                if variant_mode:
                    matched = order_lines.filtered(
                        lambda sol, av=line.attribute_value_id: (
                            av
                            in sol.product_id.product_template_attribute_value_ids.mapped(
                                "product_attribute_value_id"
                            )
                        )
                    )
                    qty = sum(matched.mapped("product_uom_qty"))
                else:
                    qty = sum(order_lines.mapped("product_uom_qty"))

                if qty < required_qty:
                    missing.append(
                        _("%(tmpl)s — %(size)s requires %(needed)s but only "
                          "%(current)s ordered")
                        % {
                            "tmpl": template.display_name,
                            "size": line.attribute_value_id.display_name,
                            "needed": required_qty,
                            "current": qty,
                        }
                    )

        # --- Complete size run -------------------------------------------
        if self.require_complete_size_run and self.attribute_id:
            ordered_sizes = set()
            for sol in order_lines:
                for ptav in sol.product_id.product_template_attribute_value_ids:
                    if ptav.attribute_id == self.attribute_id:
                        ordered_sizes.add(ptav.product_attribute_value_id.id)

            for size_id in ordered_sizes:
                matched = order_lines.filtered(
                    lambda sol, sid=size_id: sid in (
                        sol.product_id.product_template_attribute_value_ids.mapped(
                            "product_attribute_value_id"
                        ).ids
                    )
                )
                qty = sum(matched.mapped("product_uom_qty"))
                if qty < 1:
                    size_name = self.env["product.attribute.value"].browse(size_id).display_name
                    missing.append(
                        _("%(tmpl)s — size %(size)s has 0 units (complete size "
                          "run required)")
                        % {"tmpl": template.display_name, "size": size_name}
                    )

        # --- Min fill rate per style/color -------------------------------
        if self.min_fill_rate_style:
            storable_lines = order_lines.filtered(
                lambda sol: not sol.display_type
                and sol.product_id
                and sol.product_id.is_storable
            )
            ordered_qty = sum(storable_lines.mapped("product_uom_qty"))
            if ordered_qty:
                warehouse = order.warehouse_id or self.warehouse_id
                available = self._get_availability(
                    storable_lines.mapped("product_id"),
                    warehouse,
                    order.company_id,
                )
                fill = min(available / ordered_qty * 100.0, 100.0)
                if fill < self.min_fill_rate_style:
                    missing.append(
                        _("%(tmpl)s — fill rate %(fill).1f%% is below the "
                          "required %(min).1f%%")
                        % {
                            "tmpl": template.display_name,
                            "fill": fill,
                            "min": self.min_fill_rate_style,
                        }
                    )

        return missing


class ApparelAllocationRuleLine(models.Model):
    _name = "apparel.allocation.rule.line"
    _description = "Apparel Allocation Rule Line"
    _order = "sequence, id"

    name = fields.Char(
        related="attribute_value_id.name", string="Size", store=False
    )
    sequence = fields.Integer(default=10)
    rule_id = fields.Many2one(
        "apparel.allocation.rule", required=True, ondelete="cascade"
    )
    attribute_value_id = fields.Many2one(
        "product.attribute.value",
        string="Size Value",
        required=True,
        help="Specific size value that needs to be represented in the order.",
    )
    min_qty = fields.Float(
        string="Minimum Quantity",
        default=1.0,
        help="Minimum quantity for this size value.",
    )

    @api.constrains("attribute_value_id", "rule_id")
    def _check_unique_size(self):
        for line in self:
            siblings = line.rule_id.line_ids - line
            if line.attribute_value_id in siblings.mapped("attribute_value_id"):
                raise UserError(
                    _("Each size value can only appear once per rule.")
                )


class ApparelCustomerType(models.Model):
    _name = "apparel.customer.type"
    _description = "Customer Type"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
