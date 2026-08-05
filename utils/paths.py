import os

def project_root():
    return os.getcwd()

def data_path(project_name):
    return os.path.join(project_root(), project_name, "data")

def balances_path(project_name):
    return os.path.join(data_path(project_name), "Balances")

def movements_path(project_name):
    return os.path.join(data_path(project_name), "Movements")

def db_path():
    return os.path.join(project_root(), "portfolio-data", "treasury.db")