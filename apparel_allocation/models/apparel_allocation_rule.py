from odoo import api, fields, models, _
from odoo.exceptions import UserError


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
        domain=[("detailed_type", "in", ["product", "consu"])],
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
    # Allocation check (Phase 1 — still uses ordered qty logic,
    # availability-based checks will be added in Phase 3)
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
                template, template_lines, variant_mode
            )
            all_missing.extend(missing)

        if all_missing and not self.allow_partial:
            raise UserError(
                _("Allocation rule '%(rule)s' not satisfied:\n%(details)s")
                % {"rule": self.display_name, "details": "\n".join(all_missing)}
            )
        return all_missing

    def _check_template_allocation(self, template, order_lines, variant_mode):
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

        # --- Min fill rate per style/color (Phase 1 placeholder) ---------
        # Full availability-based fill rate will be computed in Phase 3
        # when the allocation engine has warehouse resolution. For now we
        # record the threshold so it is stored on the rule and ready to use.

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
