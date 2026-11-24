#!/usr/bin/env python3
"""单独测试 Decisions:POST /v1/alpha/decisions → OpenRouter /api/alpha/decisions

用法:
    set NEW_API_BASE=http://localhost:3000
    set NEW_API_KEY=sk-xxx
    python decisions_test.py

环境变量:
    DECISIONS_ALIAS   下游别名,默认 Decisions
    DECISIONS_PATH    入口路径,默认 /v1/alpha/decisions
                      可换 /openrouter/v1/alpha/decisions 验证前缀副本
"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("NEW_API_BASE", "http://localhost:3000").rstrip("/")
KEY = os.environ.get("NEW_API_KEY", "")
MODEL = os.environ.get("DECISIONS_ALIAS", "Decisions")
PATH = os.environ.get("DECISIONS_PATH", "/v1/alpha/decisions")

body = {
    "model": MODEL,
    "state": "Customer support ticket: I tried to upgrade my subscription to Team tier "
             "using my corporate credit card, but the charge failed with error code "
             "ERR_CARD_DECLINED. My invoice is now overdue and I am very frustrated.",
    "questions": {
        "department": {
            "type": "choice",
            "instructions": "Which department should handle this ticket?",
            "criteria": {
                "billing": "Invoices, credit card charges, upgrades, and payment issues.",
                "technical_support": "API bugs, latency, SDK crashes, and integration failures.",
                "sales": "Enterprise contracts, custom volume pricing, and RFPs.",
            },
        },
        "is_churn_risk": {
            "type": "noul",
            "instructions": "Is this customer expressing intent to cancel or leave the service?",
        },
        "urgency": {
            "type": "score",
            "instructions": "How urgent is this customer issue?",
            "criteria": [
                "Low priority: general inquiry or cosmetic issue",
                "Medium priority: normal workflow blocked but workaround exists",
                "High priority: critical revenue or account access blocked",
            ],
        },
    },
}

if not KEY:
    sys.exit("先设置 NEW_API_KEY")

req = urllib.request.Request(
    BASE + PATH,
    data=json.dumps(body).encode(),
    headers={
        "Authorization": "Bearer " + KEY,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 newapi-decisions-test/1.0",
    },
    method="POST",
)
print("POST %s%s  model=%s" % (BASE, PATH, MODEL))
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read())
except urllib.error.HTTPError as e:
    text = e.read().decode(errors="replace")[:800]
    if "text/html" in (e.headers.get("Content-Type") or ""):
        text = "返回的是前端 HTML —— 插件路由没注册(插件未启用或渠道未绑定)"
    sys.exit("HTTP %d: %s" % (e.code, text))

print(json.dumps(payload, ensure_ascii=False, indent=2))
