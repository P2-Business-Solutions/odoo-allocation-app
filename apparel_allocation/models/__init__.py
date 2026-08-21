from . import apparel_allocation_rule
from . import apparel_allocation
from . import res_config_settings
from . import res_partner
from . import sale_order
from . import purchase_order
from . import mrp_production

# Imported last: its init() creates a SQL view that references columns added
# by the models above (e.g. res_partner.customer_type_id), and Odoo
# initializes models in import order.
from . import apparel_allocation_report
