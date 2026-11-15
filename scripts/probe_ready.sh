#!/usr/bin/env bash
# 在 api-admin 容器内读取 live 与 ready，输出一行 JSON（供手工与 S0 验收记录使用）
set -euo pipefail
docker compose -f deploy/compose.yaml exec -T api-admin python -c "
import json, urllib.request, urllib.error
def get(path):
    try:
        r = urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=5)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
live_code, _ = get('/health/live')
code, body = get('/health/ready')
print(json.dumps({'live': live_code, 'ready': code, 'status': body['status'],
                  'checks': {c['name']: [c['status'], c['detail']] for c in body['checks']}}, ensure_ascii=False))
"
