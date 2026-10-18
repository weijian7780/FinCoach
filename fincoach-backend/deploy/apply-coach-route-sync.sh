#!/bin/sh
set -eu

app_dir=/opt/fincoach-backend
staging_dir=/home/ubuntu/fincoach-coach-route-sync
backup_dir=/opt/fincoach-backend-backups/20260810-before-coach-route-sync

for file in service.py routing.py prompts.py agent_tools.py; do
  test -s "${staging_dir}/${file}"
done

mkdir -p "${backup_dir}/rag"
if [ ! -e "${backup_dir}/rag/service.py" ]; then
  cp -p "${app_dir}/app/rag/service.py" "${backup_dir}/rag/service.py"
  cp -p "${app_dir}/app/rag/routing.py" "${backup_dir}/rag/routing.py"
  cp -p "${app_dir}/app/rag/prompts.py" "${backup_dir}/rag/prompts.py"
  cp -p "${app_dir}/app/agent_tools.py" "${backup_dir}/agent_tools.py"
fi

cp "${staging_dir}/service.py" "${app_dir}/app/rag/service.py"
cp "${staging_dir}/routing.py" "${app_dir}/app/rag/routing.py"
cp "${staging_dir}/prompts.py" "${app_dir}/app/rag/prompts.py"
cp "${staging_dir}/agent_tools.py" "${app_dir}/app/agent_tools.py"

cd "${app_dir}"
docker compose -f compose.oracle.yml up -d --build --force-recreate
printf 'COACH_ROUTE_FILES_SYNCED\n'
