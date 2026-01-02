from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    allocation_state = fields.Selection(
        [
            ("pending", "Needs Allocation"),
            ("ready", "Allocation Ready"),
        ],
        string="Allocation State",
        compute="_compute_allocation_state",
        store=True,
        readonly=True,
    )
    allocation_message = fields.Text(
        string="Allocation Notes",
        compute="_compute_allocation_state",
        store=True,
        readonly=True,
    )

    def _get_allocation_rules_by_template(self):
        rules = self.env["apparel.allocation.rule"].sudo().search(
            ["|", ("company_id", "=", False), ("company_id", "=", self.env.company.id)]
        )
        return {rule.product_template_id.id: rule for rule in rules}

    @api.depends(
        "order_line",
        "order_line.product_id",
        "order_line.product_uom_qty",
    )
    def _compute_allocation_state(self):
        for order in self:
            messages = []
            blocking = False
            rules_by_template = order._get_allocation_rules_by_template()
            templates = order.order_line.product_id.product_tmpl_id
            for template in templates:
                rule = rules_by_template.get(template.id)
                if not rule:
                    continue
                try:
                    missing = rule.check_allocation(order)
                    if missing:
                        messages.extend(missing)
                except UserError as exc:
                    messages.append(str(exc.name or exc))
                    blocking = True
            order.allocation_state = "ready" if not messages else "pending"
            order.allocation_message = "\n".join(messages)
            if blocking and order.state not in ("draft", "sent"):
                order.message_post(body=order.allocation_message)

    def _check_allocation_ready(self):
        for order in self:
            if order.allocation_state != "ready":
                msg = order.allocation_message or _("Allocation rules are not satisfied for this order.")
                raise UserError(msg)

    def action_confirm(self):
        self._check_allocation_ready()
        return super().action_confirm()
