#!/usr/bin/env bash
set -euo pipefail

archive="/home/ubuntu/fincoach-backend-oracle-arm64-balanced-reasoning-20260718.tar.gz"
app_dir="/opt/fincoach-backend"
backup_dir="/opt/fincoach-backend-backups/20260718-balanced-reasoning"

test -s "${archive}"
sudo test -f "${app_dir}/.env"

# Preserve the previous application source without copying server secrets.
sudo mkdir -p "${backup_dir}"
sudo cp -a "${app_dir}/app" "${backup_dir}/"
sudo cp -a \
  "${app_dir}/compose.oracle.yml" \
  "${app_dir}/Dockerfile.arm64" \
  "${app_dir}/requirements.txt" \
  "${backup_dir}/"

# The deployment archive deliberately excludes .env, .venv, and .git.
sudo tar --no-same-owner -xzf "${archive}" -C "${app_dir}"

if sudo grep -q '^LLM_MODEL=' "${app_dir}/.env"; then
  sudo sed -i \
    's#^LLM_MODEL=.*#LLM_MODEL=openai/gpt-oss-20b#' \
    "${app_dir}/.env"
else
  echo 'LLM_MODEL=openai/gpt-oss-20b' |
    sudo tee -a "${app_dir}/.env" >/dev/null
fi

if sudo grep -q '^LLM_MAX_TOKENS=' "${app_dir}/.env"; then
  sudo sed -i \
    's#^LLM_MAX_TOKENS=.*#LLM_MAX_TOKENS=4096#' \
    "${app_dir}/.env"
else
  echo 'LLM_MAX_TOKENS=4096' |
    sudo tee -a "${app_dir}/.env" >/dev/null
fi

sudo grep '^LLM_MODEL=' "${app_dir}/.env"
sudo grep '^LLM_MAX_TOKENS=' "${app_dir}/.env"
cd "${app_dir}"
sudo docker compose -f compose.oracle.yml up -d --build
