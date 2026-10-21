#!/bin/sh
set -eu

app_dir=/opt/fincoach-backend
nvidia_source=/opt/fincoach-backend-backups/20260810-before-deepseek/.env
backup_file=/opt/fincoach-backend-backups/20260810-before-nvidia120b-primary.env
next_env=

cleanup() {
  if [ -n "${next_env}" ]; then
    rm -f "${next_env}"
  fi
}
trap cleanup EXIT

test -s "${app_dir}/.env"
test -s "${nvidia_source}"

nvidia_key=$(sed -n 's/^LLM_API_KEY=//p' "${nvidia_source}" | head -n 1 | tr -d '\r\n')
case "${nvidia_key}" in
  nvapi-*) ;;
  *) printf 'NVIDIA_KEY_NOT_FOUND\n' >&2; exit 1 ;;
esac

if [ ! -e "${backup_file}" ]; then
  cp -p "${app_dir}/.env" "${backup_file}"
fi

next_env=$(mktemp "${app_dir}/.env.nvidia120b.XXXXXX")
sed \
  -e '/^LLM_PRIMARY_BASE_URL=/d' \
  -e '/^LLM_PRIMARY_API_KEY=/d' \
  -e '/^LLM_PRIMARY_MODEL=/d' \
  -e '/^LLM_MAX_TOKENS=/d' \
  "${app_dir}/.env" > "${next_env}"
printf 'LLM_PRIMARY_BASE_URL=https://integrate.api.nvidia.com/v1\n' >> "${next_env}"
printf 'LLM_PRIMARY_API_KEY=%s\n' "${nvidia_key}" >> "${next_env}"
printf 'LLM_PRIMARY_MODEL=openai/gpt-oss-120b\n' >> "${next_env}"
printf 'LLM_MAX_TOKENS=32768\n' >> "${next_env}"
chown --reference="${app_dir}/.env" "${next_env}"
chmod 600 "${next_env}"
mv "${next_env}" "${app_dir}/.env"
next_env=

cd "${app_dir}"
docker compose -f compose.oracle.yml up -d --build --force-recreate
grep -E '^(LLM_PRIMARY_BASE_URL|LLM_PRIMARY_MODEL|LLM_PRIMARY_TIMEOUT_SECONDS|LLM_BASE_URL|LLM_MODEL|LLM_FALLBACK_TIMEOUT_SECONDS|LLM_MAX_TOKENS|COACH_WRITE_ACTIONS_ENABLED)=' .env
printf 'NVIDIA_120B_PRIMARY_SAVED\n'
