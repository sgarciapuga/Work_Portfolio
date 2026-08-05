import os
from utils.paths import get_project_root

def get_data_path():
    return os.path.join(get_project_root(), "treasury-cashflow-simulation", "data")

def get_balances_path():
    return os.path.join(get_data_path(), "Balances")

def get_movements_path():
    return os.path.join(get_data_path(), "Movements")
