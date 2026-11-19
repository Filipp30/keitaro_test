import os

# Tests never touch the real Keitaro or the local app.db.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["KEITARO_URL"] = "https://keitaro.test"
os.environ["KEITARO_API_KEY"] = "test-key"
