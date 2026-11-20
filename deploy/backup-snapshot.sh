#!/usr/bin/env bash
# Run by the root-owned systemd backup service, with backend.env and backup.env.
set -euo pipefail
exec 9>/run/lock/smartnest-backup.lock
flock -n 9 || exit 75

backup_directory=/var/lib/smartnest/backups
mkdir -p "$backup_directory"
chgrp smartnest "$backup_directory"
chmod 750 "$backup_directory"
active_services=()
resume_services() {
  local failed=0
  for service in "${active_services[@]}"; do if ! systemctl start "$service"; then failed=1; fi; done
  active_services=()
  return "$failed"
}
trap resume_services EXIT
for service in smartnest-web.service smartnest-api.service smartnest-worker.service; do
  if systemctl is-active --quiet "$service"; then active_services+=("$service"); fi
done
for service in "${active_services[@]}"; do systemctl stop "$service"; done
snapshot="$backup_directory/smartnest_$(date -u +%Y%m%d_%H%M%S).snbackup"
cd /opt/smartnest/backend
/opt/smartnest/.venv/bin/python -B manage.py backup_smartnest --quiesced --output "$snapshot"
# Resume application access before transferring the encrypted snapshot offsite.
resume_services
if [[ -z "${SMARTNEST_OFFSITE_DEST:-}" ]]; then
  echo 'Local backup created, but offsite storage is not configured.' >&2
  exit 1
fi
rclone copyto "$snapshot" "${SMARTNEST_OFFSITE_DEST%/}/$(basename "$snapshot")"
date -u +%Y-%m-%dT%H:%M:%SZ > "$backup_directory/.last-offsite-success"
# No age-based deletion or pruning of user data or snapshots is performed.
