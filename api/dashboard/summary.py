import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from api.dashboard._base import base_handler
from lib import nurture_pg
from lib import dashboard_data as dd

def _get(qs):
    return dd.build_summary(nurture_pg)

handler = base_handler(_get)
