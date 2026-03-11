#!/bin/bash
# Apply Alembic migrations before starting the application

set -e

echo "[Migrate] Running Alembic migrations..."
alembic upgrade head

echo "[Migrate] ✅ Migrations complete"
