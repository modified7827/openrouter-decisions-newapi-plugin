# openrouter-decisions-newapi-plugin

> [new-api](https://github.com/QuantumNous/new-api) JS plugin that adds the missing gateway route for the OpenRouter Decisions API: `POST /v1/alpha/decisions` → `https://openrouter.ai/api/alpha/decisions`.

new-api 的 JS 插件：给网关注册原本不存在的 OpenRouter Decisions 结构化决策接口入口。

## 背景

new-api 内置的 OpenRouter 渠道已覆盖标准端点（chat / embeddings / rerank / images / audio / responses），这些直接配置 `model_mapping` 即可使用，**不需要插件**。

但 OpenRouter 的 [Decisions API](https://openrouter.ai/docs)（`/api/alpha/decisions`，结构化决策：输入 `state` + `questions`，输出分类/评分/布尔判断）在网关中没有对应入口路径，请求会落到前端 HTML fallback。本插件通过 new-api 的 jsplugin 原生路由机制补上这个缺口。

## 工作原理

```
客户端  POST {new-api}/v1/alpha/decisions
           │  native.decodeDecisions: 校验 body(model / questions / state)
           ▼
网关渠道  model_mapping 把下游别名 → 上游模型 id
           │  buildSubmitRequest: body 原样转发，仅替换 model
           ▼
上游    POST https://openrouter.ai/api/alpha/decisions
           │  parseSubmitResponse: 同步返回 immediate 终态(不进入任务轮询)
           ▼
客户端  ← renderDecisions: 上游响应原样透传
```

要点：

- 同时自动附送 `POST /openrouter/v1/alpha/decisions`（`{key}` 前缀副本）。
- 模型改名完全交给渠道 `model_mapping`，插件不改名；计费/日志按下游别名。
- `retainResult: false` —— Decisions 是同步接口，无任务快照可存。
- 按次固定计费：定价页直接填每次调用单价，上游 usage 仅透传不参与结算。

## 文件说明

| 文件 | 说明 |
|------|------|
| `plugin.js` | 插件本体。放入 new-api 仓库 `plugins/openrouter/` 目录使用 |
| `plugin_test.go` | Go 单元测试（依赖 new-api 源码，需放在仓库内同目录跑） |
| `verify.py` | 端到端验证脚本：逐个打网关端点，区分"路由没到上游"与"上游拒绝" |
| `decisions_test.py` | Decisions 端点单独测试 |
| `image_test.py` | 图像生成端点单独测试 |
| `plugin.js.bak` | 旧版备份，不参与部署 |

## 使用

### 1. 部署插件

把 `plugin.js` 放到 new-api 源码树的 `plugins/openrouter/plugin.js`（或按你的 new-api 版本的插件加载方式上传），在渠道中启用该插件。

### 2. 配置渠道 model_mapping

渠道模型列表与 `model_mapping` 中，把下游别名映射到上游模型，例如：

```json
{
  "Decisions": "parallel/decisions-fast:free"
}
```

客户端请求用 `model: "Decisions"`，发往上游的实际是 `parallel/decisions-fast:free`。

### 3. 调用

```bash
curl -X POST http://localhost:3000/v1/alpha/decisions \
  -H "Authorization: Bearer sk-你的new-api令牌" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Decisions",
    "state": "Customer ticket: my card was declined while upgrading; invoice overdue.",
    "questions": {
      "department": {
        "type": "choice",
        "instructions": "Which department should handle this ticket?",
        "criteria": {
          "billing": "Invoices, charges, payment issues",
          "technical_support": "API bugs, latency, crashes",
          "sales": "Contracts, volume pricing"
        }
      },
      "is_churn_risk": {
        "type": "noul",
        "instructions": "Is this customer expressing intent to cancel?"
      }
    }
  }'
```

## 验证

### 单元测试（需要 new-api 源码树）

`plugin_test.go` 依赖 `github.com/QuantumNous/new-api` 内部包，需把 `plugin.js` + `plugin_test.go` 一起放进仓库 `plugins/openrouter/` 后运行：

```bash
cd plugins/openrouter && go test -v
```

### 端到端验证（打运行中的网关）

```bash
# Windows cmd
set NEW_API_BASE=http://localhost:3000
set NEW_API_KEY=sk-你的new-api令牌
python verify.py

# 上传并启用插件后，加测 decisions 两条
set TEST_PLUGIN=1
python verify.py
```

判定口径：

- `200` → 通过；响应回显 `model` 为上游名则顺带验证 `model_mapping` 生效
- `404` / `无可用渠道` / 返回前端 HTML → 路由未注册（没到上游）
- 上游风格 `4xx` → 路由已通，是 OpenRouter 侧参数/额度问题

单独脚本：

```bash
python decisions_test.py          # 只测 decisions
python image_test.py "a cat"      # 只测生图，存 image_out.png
```

## 许可

MIT
