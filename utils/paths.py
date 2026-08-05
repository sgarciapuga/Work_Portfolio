import os

def get_project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def get_data_path():
    repo = get_project_root()
    pd = os.path.join(repo, "portfolio-data")
    if os.path.isdir(pd):
        return pd
    return os.path.join(repo, "data")

def db_path():
    return os.path.join(get_data_path(), "treasury.db")

def balances_path():
    return os.path.join(get_data_path(), "balances.csv")

def movements_path():
    return os.path.join(get_data_path(), "movements.csv")
