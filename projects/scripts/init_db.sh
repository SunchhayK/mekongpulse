#!/usr/bin/env bash
# Create the MekongPulse databases inside the shared local Postgres container.
# Schema (tables) is created automatically by the repository on first boot.
set -euo pipefail

container="${PG_CONTAINER:-pg_db}"
databases=("mekongpulse" "mekongpulse_staging")

# --fresh re-creates dev/staging databases from scratch (local scratch data only).
if [[ "${1:-}" == "--fresh" ]]; then
  for db in "${databases[@]}"; do
    docker exec "$container" dropdb --if-exists -U postgres "$db"
    echo "✖ dropped '$db' (--fresh)"
  done
fi

for db in "${databases[@]}"; do
  if docker exec "$container" psql -U postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1; then
    echo "✓ database '$db' already exists"
  else
    docker exec "$container" createdb -U postgres "$db"
    echo "✚ created database '$db'"
  fi
done

echo
echo "Verify with:"
echo "  docker exec $container psql -U postgres -d mekongpulse -c '\\dt'"
