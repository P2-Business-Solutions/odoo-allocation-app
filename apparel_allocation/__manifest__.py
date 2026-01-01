# Copyright 2024-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0.en.html).
{
    "name": "Apparel Allocation Rules",
    "summary": "Allocation controls for apparel orders before picking readiness.",
    "description": """Provide configurable allocation rules to keep apparel orders from
    reaching the Ready state until useful size assortments are reserved. A
    company can opt into product variant-aware rules or template-only rules
    depending on how sizes are modeled. Compatible with Odoo 17.0 through 19.0.""",
    "version": "17.0.1.0.0",
    "author": "OpenAI Assistant",
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
        "views/res_config_settings_views.xml",
    ],
    "application": False,
}
