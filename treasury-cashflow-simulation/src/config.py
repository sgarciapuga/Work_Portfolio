from utils.db import get_connection
from sim_paths import get_balances_path as local_get_balances_path, get_movements_path as local_get_movements_path

PROJECT_NAME = "treasury-cashflow-simulation"

def get_balances_path():
    return local_get_balances_path()

def get_movements_path():
    return local_get_movements_path()

def get_conn():
    return get_connection()
