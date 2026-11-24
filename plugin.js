// OpenRouter Decisions 代理插件。
//
// 只做一件事：给网关注册原本没有的入口
//   POST /v1/alpha/decisions → {baseUrl}/alpha/decisions
//   （即 https://openrouter.ai/api/alpha/decisions，另自动附送
//    /openrouter/v1/alpha/decisions 的 {key} 前缀副本）
//
// 模型名映射由渠道的 model_mapping 完成（下游别名 → 上游模型 id），本插件不改名：
// 计费与日志按下游名（ctx.model），上游请求体发映射名（ctx.upstreamModel）。
// chat/embeddings/rerank/images/audio 等标准端点走内置 OpenRouter 渠道，与本插件无关。

export const meta = {
  apiVersion: 1,
  key: "openrouter",
  name: "OpenRouter Decisions",
  icon: "text:OR",
  description: {
    en: "OpenRouter Decisions proxy: adds the missing /v1/alpha/decisions gateway route",
    zh: "OpenRouter Decisions 代理：补上网关缺失的 /v1/alpha/decisions 入口",
  },
  version: "1.0.3",
  author: { name: "Custom" },
  baseUrl: "https://openrouter.ai/api",

  // meta.models 是插件声称可用的模型集合：原生路由在 decode 之前就按它校验
  // 客户端的 model 字段。必须含【下游别名】（与渠道模型列表/令牌范围大小写一致），
  // 把映射尾巴也列入则直接发上游原名也能命中。
  models: [
    "Decisions",
    "parallel/decisions-fast:free",
    "typesafe/jev-1.14",
    "cloudflare/clef-flash",
    "inception/mercury-decide",
  ],

  fetchMode: "per_task",

  // 按次固定计费：不声明 usageSchema，定价页直接填 Decisions 的每调用单价；
  // 上游 usage 仅随响应透传给客户端，不参与结算。

  routes: [
    {
      method: "POST",
      path: "/v1/alpha/decisions",
      type: "submit",
      decode: "decodeDecisions",
      render: "renderDecisions",
      retainResult: false, // 同步接口、无任务可查，不持久化上游快照
    },
  ],
};

function trimmed(value) {
  return String(value || "").trim();
}

function bearer(ctx) {
  return { Authorization: "Bearer " + ctx.apiKey };
}

// ---------------------------------------------------------------------------
// Driver 钩子：把请求原样转 POST {baseUrl}/alpha/decisions，body 只换 model。
// ---------------------------------------------------------------------------

export function buildSubmitRequest(ctx) {
  const headers = Object.assign({ "Content-Type": "application/json" }, bearer(ctx));
  const body = Object.assign({}, ctx.requestBody, { model: ctx.upstreamModel || ctx.model });
  return { url: ctx.baseUrl + "/alpha/decisions", method: "POST", headers, body };
}

export function parseSubmitResponse(ctx, resp) {
  const body = resp.body || {};
  const taskId = body.id || body.request_id || "decision-" + Date.now();
  if (body.error) {
    return { taskId, taskData: body, immediate: { status: "FAILURE" } };
  }
  return { taskId, taskData: body, immediate: { status: "SUCCESS" } };
}

// decisions 在 parseSubmitResponse 里即返回 immediate 终态、不进入轮询；
// 下面两个是宿主对 task 插件的必填导出，保留最小实现即可。
export function buildQueryRequest(ctx) {
  return { url: ctx.baseUrl + "/v1/models", method: "GET", headers: bearer(ctx) };
}

export function parseTaskResult(ctx, body) {
  return { status: "UNKNOWN", reason: "decisions tasks complete synchronously" };
}

// ---------------------------------------------------------------------------
// 原生路由钩子：POST /v1/alpha/decisions 的请求解码与响应渲染。
// ---------------------------------------------------------------------------

export const native = {
  decodeDecisions: function (ctx) {
    if (!ctx.body || ctx.body.kind !== "json") throw new Error("JSON body required");
    const req = ctx.body.value;
    if (!req || typeof req !== "object" || Array.isArray(req)) throw new Error("request body must be an object");
    const model = trimmed(req.model);
    if (!model) throw new Error("model is required");
    if (!req.questions || typeof req.questions !== "object" || Array.isArray(req.questions)) throw new Error("questions must be an object");
    if (req.state === undefined) throw new Error("state is required");
    return { kind: "submit", model: model, action: "decisions", requestBody: req };
  },
  renderDecisions: function (ctx, task) {
    if (task.data && typeof task.data === "object" && !Array.isArray(task.data)) return task.data;
    return {};
  },
};
