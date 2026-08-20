# Copyright 2024-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0.en.html).
{
    "name": "Apparel Allocation & Fulfillment",
    "summary": "Size-run aware allocation against stock, purchase orders and "
               "manufacturing orders, with date matching, reporting and "
               "bulk re-allocation tools for apparel companies.",
    "description": """Apparel-specific allocation and fulfillment logic for Odoo.

    Provides:
    - An allocation ledger linking sale order demand to supply sources:
      on-hand stock, confirmed purchase orders and manufacturing orders
    - Date-based matching of future supply against order commitment dates
    - Bulk allocation / re-allocation wizards (by priority, commitment date)
    - Individual re-allocation (release or move to another source)
    - Allocation analysis reporting (pivot / graph) including unallocated demand
    - Configurable allocation rules with customer eligibility filters,
      size-run completeness checks and availability-based fill-rate thresholds
    - Soft (ledger) and hard (stock reservation) allocation modes
    """,
    "version": "19.0.3.0.0",
    "author": "P2 Business Solutions",
    "license": "AGPL-3",
    "category": "Inventory/Inventory",
    "depends": [
        "base",
        "sale_management",
        "sale_stock",
        "stock",
        "product",
        "purchase",
        "mrp",
    ],
    "data": [
        "security/apparel_allocation_security.xml",
        "security/ir.model.access.csv",
        "data/apparel_allocation_data.xml",
        "views/apparel_allocation_rule_views.xml",
        "views/apparel_allocation_views.xml",
        "views/apparel_allocation_wizard_views.xml",
        "views/apparel_allocation_report_views.xml",
        "views/sale_order_views.xml",
        "views/purchase_order_views.xml",
        "views/mrp_production_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "application": True,
    "installable": True,
}
