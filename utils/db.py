import os
import sqlite3

def db_path():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    portfolio_path = os.path.join(repo_root, "portfolio-data")
    data_root = portfolio_path if os.path.isdir(portfolio_path) else os.path.join(repo_root, "data")
    return os.path.join(data_root, "treasury.db")

def get_connection():
    p = db_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return sqlite3.connect(p)
