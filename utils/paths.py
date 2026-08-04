import os

def get_project_root():
    # Case 1: R Markdown passes the root
    if "PROJECT_ROOT" in os.environ:
        return os.environ["PROJECT_ROOT"]

    # Case 2: Python script knows its own location
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_db_path():
    root = get_project_root()
    return os.path.join(root, "portfolio-data", "treasury.db")