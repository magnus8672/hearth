"""Run the Python suite in the isolated Linux development container against its real database."""

import os
import subprocess
import sys

if os.environ.get("HEARTH_PROBE_ENVIRONMENT") != "isolated_development_container":
    raise SystemExit("This probe is restricted to the explicit isolated development container.")

os.environ["HEARTH_REQUIRE_INTEGRATIONS"] = "1"
os.environ["HEARTH_TEST_APP_DATABASE_URL"] = f"postgresql+psycopg://hearth_app:{os.environ['HEARTH_APP_PASSWORD']}@postgres:5432/hearth"
os.environ["HEARTH_TEST_MIGRATION_DATABASE_URL"] = f"postgresql+psycopg://hearth_migrator:{os.environ['HEARTH_MIGRATION_PASSWORD']}@postgres:5432/hearth"
subprocess.run([sys.executable, "-m", "pytest", "-q", "--junitxml=.hearth/test-results/linux-python.xml"], check=True)
