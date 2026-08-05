import sqlite3
from .paths import db_path

def get_connection():
    return sqlite3.connect(db_path())