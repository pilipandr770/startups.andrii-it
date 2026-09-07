#!/bin/sh
set -e

# Idempotent — `flask db upgrade` is a no-op if the DB is already at head.
# Runs on every container start so a redeploy can never forget this step.
echo "Running database migrations..."
flask db upgrade

exec "$@"
