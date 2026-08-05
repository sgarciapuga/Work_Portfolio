import os
import pandas as pd
from sim_paths import get_data_path

PROJECT_NAME = "treasury-cashflow-simulation"

def load_static_data():
    setup_file = os.path.join(get_data_path(), "setup.xlsx")

    accounts = pd.read_excel(setup_file, sheet_name="Static_Data_Bank_Accounts")
    accounts["account_number"] = accounts["account_number"].astype(str)

    movement_types = pd.read_excel(setup_file, sheet_name="Type Movements")

    return accounts, movement_types
