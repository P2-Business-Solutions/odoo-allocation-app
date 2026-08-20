# odoo-allocation-app

Inventory and order **allocation for apparel companies** on **Odoo 19**, packaged as the
`apparel_allocation` add-on.

The app links sale-order demand to supply — on-hand stock, confirmed **purchase orders**
and **manufacturing orders** — through a soft-allocation ledger, with date-based matching
of future supply, bulk allocation / re-allocation tools, and dedicated reporting.

## Features

### Allocation engine (stock / PO / MO)
- Allocates open sale-order demand against three supply sources, in date order:
  on-hand stock first, then the earliest purchase-order lines and manufacturing orders.
- Each source can be toggled globally (Settings) or per run (wizard), so you can
  allocate on POs and/or MOs — or on-hand stock only.
- **Date matching**: optionally only match future supply whose expected date
  (PO *Expected Arrival* / MO *Finish Date*) falls on or before the order's
  commitment date, with a configurable tolerance in days. A supply-horizon limit
  (N days) is also available.
- Over-allocation of a PO line or MO is blocked by capacity constraints; allocations
  are released automatically when the sale order, purchase order, or manufacturing
  order is cancelled.
- Soft allocations live in a ledger (`apparel.allocation`); an optional hard mode
  additionally reserves stock on the delivery pickings of confirmed orders.
- Optional auto-allocation when a sale order is confirmed.

### Re-allocation (individual & bulk)
- **Bulk**: the *Run Allocation* wizard (menu, or the *Allocate* action on selected
  sale orders) can release existing allocations and redistribute supply in a chosen
  priority sequence — earliest commitment date, order priority, or oldest order.
- **Individual**: the *Reallocate* wizard (available on selected allocations) either
  releases allocations or moves them to another source (stock, a specific PO line,
  or a specific MO), with capacity validation.
- Release buttons are available on each allocation and on the sale order.

### Reporting
- **Allocation Analysis** (pivot / graph / list): every allocation by source type
  plus the remaining *unallocated* demand of open orders — measure coverage,
  fill rates, late supply, and slice by product, customer, customer type,
  warehouse, source, or month.
- Sale orders carry an **allocation coverage** badge (none / partial / full) and an
  allocated % (list + form), with matching search filters.
- Smart buttons on sale orders, purchase orders and manufacturing orders open the
  related allocations; PO lines and MOs expose allocated / still-available quantities.
- Allocations are marked *Fulfilled* by a daily cron once their sale line is delivered.

### Allocation rules (order gating)
- Configurable rules validate orders before confirmation: customer eligibility
  (tags, customer types), complete size runs, per-size minimums, and
  availability-based fill-rate thresholds per style and per order
  (on-hand + incoming supply within the rule's lookahead window).
- Variant-aware or template-total evaluation, globally or per rule.

## Configuration

**Settings > Apparel Allocation**:
- Use product variants for allocation checks
- Default incoming-stock lookahead (days)
- Allocate from purchase orders / manufacturing orders (both enabled by default)
- Match future supply by date + tolerance (days)
- Auto-allocate on order confirmation

**Security groups** (Apparel Allocation category):
- *User* — view/run allocations, release and reallocate
- *Manager* — additionally configure allocation rules and customer types

## Running in an Odoo sandbox (19)

1. Add this repo to your Odoo server's addons path (copy or symlink the
   ``apparel_allocation`` folder next to your other custom modules).
2. Start Odoo including this addons path, e.g.
   ``odoo-bin -c /path/to/odoo.conf --addons-path=/path/to/odoo/addons,/path/to/custom/addons``.
3. Install or upgrade the module:
   ``odoo-bin -c /path/to/odoo.conf -d <db_name> -u apparel_allocation``.
   Dependencies: ``sale_management``, ``sale_stock``, ``stock``, ``purchase``, ``mrp``.
4. Open the **Apparel Allocation** app menu: *Allocations*, *Run Allocation*,
   *Allocation Rules*, *Reporting > Allocation Analysis*, *Configuration*.

## Tests

Unit tests cover the engine (stock/PO/MO sourcing, date matching and tolerance,
release/re-allocation, capacity constraints), the bulk-run wizard's priority
sequencing, the reallocation wizard, and the analysis report:

```bash
odoo-bin -c /path/to/odoo.conf -d <db_name> -u apparel_allocation --test-tags /apparel_allocation --stop-after-init
```

## Notes & known behavior

- Quantities are compared in each product's unit of measure; the engine is designed
  for unit-based apparel products.
- Soft allocations are counted against free stock. Once a confirmed order's picking
  hard-reserves stock, the window until delivery is counted conservatively
  (reservation and soft allocation both reduce availability); the daily cron closes
  allocations of delivered lines.
