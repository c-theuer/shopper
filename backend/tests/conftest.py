import os

# Integration tests run against the compose Postgres, in a separate database, with the rules agent.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5433")
os.environ.setdefault("DB_PASSWORD", "shopper")
os.environ["DB_NAME"] = "shopper_test"
os.environ["ANTHROPIC_API_KEY"] = ""
