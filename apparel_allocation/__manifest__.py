# Copyright 2024-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0.en.html).
{
    "name": "Apparel Allocation & Fulfillment",
    "summary": "Size-run aware allocation, fill-rate rules, and fulfillment "
               "controls for apparel orders.",
    "description": """Apparel-specific allocation and fulfillment logic for Odoo.

    Provides configurable allocation rules with:
    - Customer eligibility filters (tags, customer types)
    - Size-run completeness checks
    - Fill-rate thresholds per style/color and per order
    - Soft (ledger) and hard (stock reservation) allocation modes
    - Warehouse-aware availability resolution
    - Incoming-stock lookahead
    """,
    "version": "19.0.2.0.0",
    "author": "P2 Business Solutions",
    "license": "AGPL-3",
    "depends": [
        "base",
        "sale_management",
        "stock",
        "product",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/apparel_allocation_rule_views.xml",
        "views/sale_order_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "application": True,
    "installable": True,
}
