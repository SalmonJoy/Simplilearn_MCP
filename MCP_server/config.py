from settings import env

HRMS_URL = env("HRMS_URL", "http://127.0.0.1:8001").rstrip("/")
INVENTORY_URL = env("INVENTORY_URL", "http://127.0.0.1:8002").rstrip("/")
