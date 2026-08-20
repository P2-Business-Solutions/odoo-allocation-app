from odoo import fields, models, tools


class ApparelAllocationReport(models.Model):
    _name = "apparel.allocation.report"
    _description = "Apparel Allocation Analysis"
    _auto = False
    _rec_name = "product_id"
    _order = "date_needed, id"

    product_id = fields.Many2one("product.product", string="Variant", readonly=True)
    product_tmpl_id = fields.Many2one(
        "product.template", string="Product", readonly=True
    )
    sale_order_id = fields.Many2one("sale.order", string="Sale Order", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    customer_type_id = fields.Many2one(
        "apparel.customer.type", string="Customer Type", readonly=True
    )
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    source_type = fields.Selection(
        [
            ("stock", "On-Hand Stock"),
            ("purchase", "Purchase Order"),
            ("manufacture", "Manufacturing Order"),
            ("unallocated", "Unallocated"),
        ],
        string="Source",
        readonly=True,
    )
    allocation_state = fields.Selection(
        [
            ("allocated", "Allocated"),
            ("done", "Fulfilled"),
        ],
        string="Allocation Status",
        readonly=True,
    )
    order_state = fields.Selection(
        [
            ("draft", "Quotation"),
            ("sent", "Quotation Sent"),
            ("sale", "Sales Order"),
            ("cancel", "Cancelled"),
        ],
        string="Order Status",
        readonly=True,
    )
    qty = fields.Float(string="Quantity", readonly=True)
    date_expected = fields.Datetime(string="Expected Date", readonly=True)
    date_needed = fields.Datetime(string="Needed Date", readonly=True)
    is_late = fields.Boolean(string="Late Source", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    aa.id AS id,
                    aa.product_id AS product_id,
                    pp.product_tmpl_id AS product_tmpl_id,
                    aa.sale_order_id AS sale_order_id,
                    so.partner_id AS partner_id,
                    rp.customer_type_id AS customer_type_id,
                    aa.warehouse_id AS warehouse_id,
                    aa.company_id AS company_id,
                    aa.source_type AS source_type,
                    aa.state AS allocation_state,
                    so.state AS order_state,
                    aa.qty AS qty,
                    aa.date_expected AS date_expected,
                    so.commitment_date AS date_needed,
                    COALESCE(
                        aa.date_expected IS NOT NULL
                        AND so.commitment_date IS NOT NULL
                        AND aa.date_expected > so.commitment_date,
                        FALSE
                    ) AS is_late
                FROM apparel_allocation aa
                JOIN sale_order so ON so.id = aa.sale_order_id
                JOIN res_partner rp ON rp.id = so.partner_id
                JOIN product_product pp ON pp.id = aa.product_id
                WHERE aa.state != 'cancelled'

                UNION ALL

                SELECT * FROM (
                    SELECT
                        -sol.id AS id,
                        sol.product_id AS product_id,
                        pp.product_tmpl_id AS product_tmpl_id,
                        sol.order_id AS sale_order_id,
                        so.partner_id AS partner_id,
                        rp.customer_type_id AS customer_type_id,
                        so.warehouse_id AS warehouse_id,
                        so.company_id AS company_id,
                        'unallocated' AS source_type,
                        NULL AS allocation_state,
                        so.state AS order_state,
                        GREATEST(
                            sol.product_uom_qty
                            - COALESCE(sol.qty_delivered, 0)
                            - COALESCE(
                                (
                                    SELECT SUM(a2.qty)
                                    FROM apparel_allocation a2
                                    WHERE a2.sale_line_id = sol.id
                                      AND a2.state != 'cancelled'
                                ),
                                0
                            ),
                            0
                        ) AS qty,
                        NULL::timestamp AS date_expected,
                        so.commitment_date AS date_needed,
                        FALSE AS is_late
                    FROM sale_order_line sol
                    JOIN sale_order so ON so.id = sol.order_id
                    JOIN res_partner rp ON rp.id = so.partner_id
                    JOIN product_product pp ON pp.id = sol.product_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    WHERE so.state IN ('draft', 'sent', 'sale')
                      AND sol.display_type IS NULL
                      AND pt.is_storable = TRUE
                ) open_demand
                WHERE open_demand.qty > 0
            )
            """
            % self._table
        )
