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
    apparel_allocate_from_po = fields.Boolean(
        string="Allocate From Purchase Orders",
        config_parameter="apparel_allocation.allocate_from_po",
        help="Allow the allocation engine to allocate sale order demand "
             "against confirmed purchase orders (future inventory).",
    )
    apparel_allocate_from_mo = fields.Boolean(
        string="Allocate From Manufacturing Orders",
        config_parameter="apparel_allocation.allocate_from_mo",
        help="Allow the allocation engine to allocate sale order demand "
             "against confirmed manufacturing orders (future inventory).",
    )
    apparel_enforce_date_match = fields.Boolean(
        string="Match Future Supply By Date",
        config_parameter="apparel_allocation.enforce_date_match",
        help="Only allocate future supply (POs/MOs) expected on or before "
             "the order's commitment date, plus the tolerance below.",
    )
    apparel_date_tolerance_days = fields.Integer(
        string="Date Match Tolerance (days)",
        config_parameter="apparel_allocation.date_tolerance_days",
        help="When matching future supply by date, allow sources expected up "
             "to this many days after the order's commitment date.",
    )
    apparel_auto_allocate_on_confirm = fields.Boolean(
        string="Auto-Allocate On Order Confirmation",
        config_parameter="apparel_allocation.auto_allocate_on_confirm",
        help="Automatically run the allocation engine when a sale order is "
             "confirmed.",
    )
