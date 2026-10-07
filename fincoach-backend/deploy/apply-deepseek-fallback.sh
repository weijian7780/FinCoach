#!/bin/sh
set -eu

app_dir=/opt/fincoach-backend
staging_dir=/home/ubuntu/fincoach-deepseek-deploy
transfer_file=/home/ubuntu/.fincoach-deepseek-key-transfer
backup_dir=/opt/fincoach-backend-backups/20260810-before-deepseek
next_env=
next_llm=

cleanup() {
  rm -f "${transfer_file}"
  if [ -n "${next_env}" ]; then
    rm -f "${next_env}"
  fi
  if [ -n "${next_llm}" ]; then
    rm -f "${next_llm}"
  fi
}
trap cleanup EXIT

test -s "${transfer_file}"
test -s "${staging_dir}/llm.py"

mkdir -p "${backup_dir}"
if [ ! -e "${backup_dir}/llm.py" ]; then
  cp -p "${app_dir}/app/llm.py" "${backup_dir}/llm.py"
fi
if [ ! -e "${backup_dir}/.env" ]; then
  cp -p "${app_dir}/.env" "${backup_dir}/.env"
fi

next_llm=$(mktemp "${app_dir}/app/llm.py.deepseek.XXXXXX")
cp "${staging_dir}/llm.py" "${next_llm}"
chown --reference="${app_dir}/app/llm.py" "${next_llm}"
chmod --reference="${app_dir}/app/llm.py" "${next_llm}"
mv "${next_llm}" "${app_dir}/app/llm.py"
next_llm=

next_env=$(mktemp "${app_dir}/.env.deepseek.XXXXXX")
sed \
  -e '/^LLM_API_KEY=/d' \
  -e 's#^LLM_BASE_URL=.*#LLM_BASE_URL=https://api.deepseek.com#' \
  -e 's#^LLM_MODEL=.*#LLM_MODEL=deepseek-v4-flash#' \
  "${app_dir}/.env" > "${next_env}"
printf 'LLM_API_KEY=' >> "${next_env}"
tr -d '\r\n' < "${transfer_file}" >> "${next_env}"
printf '\n' >> "${next_env}"
chown --reference="${app_dir}/.env" "${next_env}"
chmod 600 "${next_env}"
mv "${next_env}" "${app_dir}/.env"
next_env=

cd "${app_dir}"
docker compose -f compose.oracle.yml up -d --build --force-recreate
grep -E '^(LLM_PRIMARY_MODEL|LLM_BASE_URL|LLM_MODEL|COACH_WRITE_ACTIONS_ENABLED)=' .env
printf 'DEEPSEEK_KEY_SAVED\n'
