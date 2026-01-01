# odoo-allocation-app

Main purpose is for allowing for proper inventory and order allocation for apparel-based companies.

This repository now contains the ``apparel_allocation`` Odoo add-on. The module adds configurable
allocation rules that keep sale orders in a "Needs Allocation" state until size targets are met.
Administrators can decide whether to evaluate variant-level quantities or only template totals for
companies that do not use product variants.

## Running in an Odoo sandbox (17-19)

1. Add this repo to your Odoo server's addons path (copy or symlink the ``apparel_allocation``
   folder next to your other custom modules).
2. Start Odoo with the database you want to test and include this module in the addons path, e.g.
   ``odoo-bin -c /path/to/odoo.conf --addons-path=/path/to/odoo/addons,/path/to/custom/addons``.
3. Upgrade the module in your sandbox database:
   ``odoo-bin -c /path/to/odoo.conf -d <db_name> -u apparel_allocation``.
4. In Odoo, enable developer mode, open **Settings > Technical > Database Structure > Modules**, and
   verify that *Apparel Allocation Rules* is installed (install if not). The module will add menu
   items under **Inventory > Configuration > Apparel Allocation Rules** and a toggle in
   **Settings > Sales** to choose variant-aware checks.
5. Create allocation rules for your apparel products, then confirm a sale order; the order will only
   reach *Ready* once its lines meet the size/variant targets configured for the products.
