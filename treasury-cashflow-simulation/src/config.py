from utils.db import get_connection
from utils.paths import balances_path, movements_path

PROJECT_NAME = "treasury-cashflow-simulation"

def get_balances_path():
    return balances_path(PROJECT_NAME)

def get_movements_path():
    return movements_path(PROJECT_NAME)

def get_conn():
    return get_connection()