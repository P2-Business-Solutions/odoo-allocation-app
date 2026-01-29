from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    customer_type_id = fields.Many2one(
        "apparel.customer.type",
        string="Customer Type",
        help="Classification used by apparel allocation rules "
             "(e.g., Wholesale, Distributor, Retail).",
    )
