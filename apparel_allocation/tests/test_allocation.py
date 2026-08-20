from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestApparelAllocation(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Apparel Test Tee (M)",
                "type": "consu",
                "is_storable": True,
            }
        )
        cls.customer = cls.env["res.partner"].create({"name": "Test Retailer"})
        cls.vendor = cls.env["res.partner"].create({"name": "Test Vendor"})
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.warehouse.lot_stock_id, 5.0
        )
        cls.Allocation = cls.env["apparel.allocation"]

    def _create_so(self, qty, commitment=None):
        return self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "commitment_date": commitment,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": qty,
                        }
                    )
                ],
            }
        )

    def _create_po(self, qty, date_planned):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": qty,
                            "price_unit": 5.0,
                            "date_planned": date_planned,
                        }
                    )
                ],
            }
        )
        po.button_confirm()
        return po

    def _create_mo(self, qty):
        mo = self.env["mrp.production"].create(
            {
                "product_id": self.product.id,
                "product_qty": qty,
            }
        )
        mo.action_confirm()
        return mo

    # ------------------------------------------------------------------
    # Engine
    # ------------------------------------------------------------------
    def test_allocate_from_stock(self):
        so = self._create_so(3)
        created = self.Allocation.allocate_sale_lines(so.order_line)
        self.assertEqual(len(created), 1)
        self.assertEqual(created.source_type, "stock")
        self.assertEqual(created.qty, 3.0)
        self.assertEqual(so.allocation_coverage, "full")
        self.assertAlmostEqual(so.allocation_pct, 100.0)

    def test_allocate_stock_then_purchase(self):
        self._create_po(10, fields.Datetime.now() + timedelta(days=10))
        so = self._create_so(12)
        created = self.Allocation.allocate_sale_lines(so.order_line)
        by_source = {a.source_type: a.qty for a in created}
        self.assertEqual(by_source.get("stock"), 5.0)
        self.assertEqual(by_source.get("purchase"), 7.0)
        self.assertEqual(so.allocation_coverage, "full")

    def test_allocate_from_manufacturing(self):
        mo = self._create_mo(4)
        so = self._create_so(9)
        created = self.Allocation.allocate_sale_lines(
            so.order_line, source_purchase=False
        )
        by_source = {a.source_type: a.qty for a in created}
        self.assertEqual(by_source.get("stock"), 5.0)
        self.assertEqual(by_source.get("manufacture"), 4.0)
        self.assertEqual(mo.qty_allocated, 4.0)

    def test_date_matching_skips_late_supply(self):
        self._create_po(10, fields.Datetime.now() + timedelta(days=30))
        so = self._create_so(
            12, commitment=fields.Datetime.now() + timedelta(days=5)
        )
        created = self.Allocation.allocate_sale_lines(
            so.order_line, enforce_date_match=True, tolerance_days=0
        )
        # Only the on-hand 5 units qualify: the PO arrives after commitment.
        self.assertEqual(len(created), 1)
        self.assertEqual(created.source_type, "stock")
        self.assertEqual(created.qty, 5.0)
        self.assertEqual(so.allocation_coverage, "partial")

    def test_date_tolerance_allows_late_supply(self):
        self._create_po(10, fields.Datetime.now() + timedelta(days=30))
        so = self._create_so(
            12, commitment=fields.Datetime.now() + timedelta(days=5)
        )
        created = self.Allocation.allocate_sale_lines(
            so.order_line, enforce_date_match=True, tolerance_days=40
        )
        self.assertEqual(
            {a.source_type for a in created}, {"stock", "purchase"}
        )
        self.assertEqual(so.allocation_coverage, "full")

    def test_release_frees_supply(self):
        so1 = self._create_so(5)
        created = self.Allocation.allocate_sale_lines(so1.order_line)
        self.assertEqual(created.qty, 5.0)
        # All stock is taken now.
        so2 = self._create_so(2)
        none_created = self.Allocation.allocate_sale_lines(
            so2.order_line, source_purchase=False, source_manufacture=False
        )
        self.assertFalse(none_created)
        # Release and re-allocate.
        created.action_release()
        self.assertEqual(created.state, "cancelled")
        again = self.Allocation.allocate_sale_lines(
            so2.order_line, source_purchase=False, source_manufacture=False
        )
        self.assertEqual(again.qty, 2.0)

    def test_purchase_capacity_constraint(self):
        po = self._create_po(4, fields.Datetime.now() + timedelta(days=10))
        so = self._create_so(3)
        with self.assertRaises(ValidationError):
            self.Allocation.create(
                {
                    "sale_line_id": so.order_line.id,
                    "product_id": self.product.id,
                    "qty": 6.0,
                    "source_type": "purchase",
                    "purchase_line_id": po.order_line.id,
                }
            )

    def test_order_cancel_releases_allocations(self):
        so = self._create_so(3)
        created = self.Allocation.allocate_sale_lines(so.order_line)
        so._action_cancel()
        self.assertEqual(created.state, "cancelled")

    # ------------------------------------------------------------------
    # Reallocation wizard
    # ------------------------------------------------------------------
    def test_reallocate_change_source(self):
        po = self._create_po(10, fields.Datetime.now() + timedelta(days=10))
        so = self._create_so(4)
        created = self.Allocation.allocate_sale_lines(
            so.order_line, source_purchase=False, source_manufacture=False
        )
        self.assertEqual(created.source_type, "stock")
        wizard = self.env["apparel.allocation.reallocate"].create(
            {
                "allocation_ids": [Command.set(created.ids)],
                "mode": "change_source",
                "new_source_type": "purchase",
                "new_purchase_line_id": po.order_line.id,
            }
        )
        wizard.action_apply()
        self.assertEqual(created.state, "cancelled")
        new_alloc = so.allocation_ids.filtered(
            lambda a: a.state == "allocated"
        )
        self.assertEqual(new_alloc.source_type, "purchase")
        self.assertEqual(new_alloc.qty, 4.0)
        self.assertEqual(new_alloc.purchase_line_id, po.order_line)

    # ------------------------------------------------------------------
    # Run wizard (bulk, priority order)
    # ------------------------------------------------------------------
    def test_bulk_run_wizard_commitment_priority(self):
        # Two orders competing for the same 5 on-hand units; the earlier
        # commitment date must be served first.
        so_late = self._create_so(
            4, commitment=fields.Datetime.now() + timedelta(days=20)
        )
        so_early = self._create_so(
            4, commitment=fields.Datetime.now() + timedelta(days=2)
        )
        wizard = self.env["apparel.allocation.run"].create(
            {
                "order_ids": [Command.set((so_late + so_early).ids)],
                "source_stock": True,
                "source_purchase": False,
                "source_manufacture": False,
                "sort_by": "commitment_date",
            }
        )
        wizard.action_run()
        early_alloc = sum(
            so_early.allocation_ids.filtered(
                lambda a: a.state == "allocated"
            ).mapped("qty")
        )
        late_alloc = sum(
            so_late.allocation_ids.filtered(
                lambda a: a.state == "allocated"
            ).mapped("qty")
        )
        self.assertEqual(early_alloc, 4.0)
        self.assertEqual(late_alloc, 1.0)

    def test_bulk_run_wizard_allocation_priority(self):
        so_normal = self._create_so(4)
        so_critical = self._create_so(4)
        so_critical.allocation_priority = "2"
        wizard = self.env["apparel.allocation.run"].create(
            {
                "order_ids": [Command.set((so_normal + so_critical).ids)],
                "source_stock": True,
                "source_purchase": False,
                "source_manufacture": False,
                "sort_by": "priority",
            }
        )
        wizard.action_run()
        critical_alloc = sum(
            so_critical.allocation_ids.filtered(
                lambda a: a.state == "allocated"
            ).mapped("qty")
        )
        normal_alloc = sum(
            so_normal.allocation_ids.filtered(
                lambda a: a.state == "allocated"
            ).mapped("qty")
        )
        self.assertEqual(critical_alloc, 4.0)
        self.assertEqual(normal_alloc, 1.0)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def test_report_rows(self):
        self._create_po(10, fields.Datetime.now() + timedelta(days=10))
        so = self._create_so(12)
        self.Allocation.allocate_sale_lines(
            so.order_line, source_manufacture=False
        )
        self.env.flush_all()
        rows = self.env["apparel.allocation.report"].search(
            [("sale_order_id", "=", so.id)]
        )
        by_source = {}
        for row in rows:
            by_source[row.source_type] = by_source.get(row.source_type, 0.0) + row.qty
        self.assertEqual(by_source.get("stock"), 5.0)
        self.assertEqual(by_source.get("purchase"), 7.0)
        self.assertFalse(by_source.get("unallocated"))

    def test_report_unallocated_demand(self):
        so = self._create_so(8)
        self.Allocation.allocate_sale_lines(
            so.order_line, source_purchase=False, source_manufacture=False
        )
        self.env.flush_all()
        rows = self.env["apparel.allocation.report"].search(
            [("sale_order_id", "=", so.id), ("source_type", "=", "unallocated")]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.qty, 3.0)
