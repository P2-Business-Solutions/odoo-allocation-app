from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    use_apparel_product_variants = fields.Boolean(
        string="Use Product Variants for Apparel Allocation",
        config_parameter="apparel_allocation.use_product_variants",
        help="When enabled, allocation rules evaluate individual product "
             "variants (e.g., sizes). When disabled, rules operate on "
             "template totals.",
    )
    apparel_default_incoming_days = fields.Integer(
        string="Default Incoming Stock Lookahead (days)",
        config_parameter="apparel_allocation.default_incoming_days",
        help="Default number of days to look ahead for incoming stock. "
             "Individual rules can override this value.",
    )
