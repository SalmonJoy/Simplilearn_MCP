from settings import env

HRMS_URL = env("HRMS_URL", "http://127.0.0.1:8001").rstrip("/")
INVENTORY_URL = env("INVENTORY_URL", "http://127.0.0.1:8002").rstrip("/")
MONGODB_URI = env("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE = env("MONGODB_DATABASE", "mcp_learning")
