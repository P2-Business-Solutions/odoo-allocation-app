from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApparelAllocationRule(models.Model):
    _name = "apparel.allocation.rule"
    _description = "Apparel Allocation Rule"
    _order = "product_template_id, sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company
    )
    product_template_id = fields.Many2one(
        "product.template",
        string="Product Template",
        required=True,
        domain=[("detailed_type", "in", ["product", "consu"])],
    )
    attribute_id = fields.Many2one(
        "product.attribute",
        string="Size Attribute",
        help="Attribute that represents apparel sizing for this rule."
    )
    allow_partial = fields.Boolean(
        string="Allow Partial Allocation",
        help="If enabled, the order can be confirmed even when some size targets are not met.",
    )
    use_variants = fields.Boolean(
        string="Use Product Variants",
        help="Override the global setting for this rule."
    )
    line_ids = fields.One2many(
        "apparel.allocation.rule.line",
        "rule_id",
        string="Size Targets",
        copy=True,
    )

    _sql_constraints = [
        ("product_company_unique", "unique(product_template_id, company_id)", "Only one rule per product template and company is allowed."),
    ]

    @api.model
    def _get_use_variants(self):
        param_value = self.env["ir.config_parameter"].sudo().get_param(
            "apparel_allocation.use_product_variants", default="False"
        )
        return param_value.lower() == "true"

    def is_variant_enabled(self):
        self.ensure_one()
        if self.use_variants:
            return True
        return self._get_use_variants()

    def check_allocation(self, order):
        self.ensure_one()
        variant_mode = self.is_variant_enabled()
        missing_targets = []
        for line in self.line_ids:
            required_qty = line.min_qty
            if variant_mode:
                matched_lines = order.order_line.filtered(
                    lambda sol: sol.product_id.product_tmpl_id == self.product_template_id
                    and line.attribute_value_id in sol.product_id.product_template_attribute_value_ids.mapped(
                        "product_attribute_value_id"
                    )
                )
                delivered_qty = sum(matched_lines.mapped("product_uom_qty"))
                if delivered_qty < required_qty:
                    missing_targets.append(
                        _("%(size)s requires %(needed)s but only %(current)s planned")
                        % {
                            "size": line.attribute_value_id.display_name,
                            "needed": required_qty,
                            "current": delivered_qty,
                        }
                    )
            else:
                template_lines = order.order_line.filtered(
                    lambda sol: sol.product_id.product_tmpl_id == self.product_template_id
                )
                total_qty = sum(template_lines.mapped("product_uom_qty"))
                if total_qty < required_qty:
                    missing_targets.append(
                        _("%(size)s target %(needed)s not met for template (total: %(current)s)")
                        % {"size": line.display_name, "needed": required_qty, "current": total_qty}
                    )
        if missing_targets and not self.allow_partial:
            raise UserError(
                _("Allocation rule '%(rule)s' not satisfied:\n%(details)s")
                % {"rule": self.display_name, "details": "\n".join(missing_targets)}
            )
        return missing_targets


class ApparelAllocationRuleLine(models.Model):
    _name = "apparel.allocation.rule.line"
    _description = "Apparel Allocation Rule Line"
    _order = "sequence, id"

    name = fields.Char(related="attribute_value_id.name", string="Size", store=False)
    sequence = fields.Integer(default=10)
    rule_id = fields.Many2one("apparel.allocation.rule", required=True, ondelete="cascade")
    attribute_value_id = fields.Many2one(
        "product.attribute.value",
        string="Size Value",
        required=True,
        help="Specific size value that needs to be represented in the order.",
    )
    min_qty = fields.Float(
        string="Minimum Quantity",
        default=1.0,
        help="Minimum quantity for this size value when variants are used. When variants are disabled, the total quantity for the template must meet this number.",
    )

    @api.constrains("attribute_value_id", "rule_id")
    def _check_unique_size(self):
        for line in self:
            siblings = line.rule_id.line_ids - line
            if line.attribute_value_id in siblings.mapped("attribute_value_id"):
                raise UserError(_("Each size value can only appear once per rule."))
