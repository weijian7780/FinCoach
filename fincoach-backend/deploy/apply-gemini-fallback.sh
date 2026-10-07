#!/bin/sh
set -eu

app_dir=/opt/fincoach-backend
transfer_file=/home/ubuntu/.fincoach-gemini-key-transfer
backup_file=/opt/fincoach-backend-backups/20260809-before-gemini-key-transfer.env
next_env=

cleanup() {
  rm -f "${transfer_file}"
  if [ -n "${next_env}" ]; then
    rm -f "${next_env}"
  fi
}
trap cleanup EXIT

test -s "${transfer_file}"
mkdir -p /opt/fincoach-backend-backups
if [ ! -e "${backup_file}" ]; then
  cp -p "${app_dir}/.env" "${backup_file}"
fi

next_env=$(mktemp "${app_dir}/.env.gemini.XXXXXX")
sed \
  -e '/^LLM_API_KEY=/d' \
  -e 's#^LLM_BASE_URL=.*#LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/#' \
  -e 's#^LLM_MODEL=.*#LLM_MODEL=gemini-3.5-flash-lite#' \
  "${app_dir}/.env" > "${next_env}"
printf 'LLM_API_KEY=' >> "${next_env}"
tr -d '\r\n' < "${transfer_file}" >> "${next_env}"
printf '\n' >> "${next_env}"
chown --reference="${app_dir}/.env" "${next_env}"
chmod 600 "${next_env}"
mv "${next_env}" "${app_dir}/.env"
next_env=

cd "${app_dir}"
docker compose -f compose.oracle.yml up -d --force-recreate
grep -E '^(LLM_PRIMARY_MODEL|LLM_BASE_URL|LLM_MODEL)=' .env
echo GEMINI_KEY_SAVED
