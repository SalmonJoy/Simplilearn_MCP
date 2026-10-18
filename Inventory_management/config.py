from settings import env

MONGODB_URI = env("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE = env("MONGODB_DATABASE", "mcp_learning")
HRMS_URL = env("HRMS_URL", "http://127.0.0.1:8001").rstrip("/")
