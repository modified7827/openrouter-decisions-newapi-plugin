#!/usr/bin/env python3
"""验证 new-api → OpenRouter 各端点路由与模型映射。

【原生可用】内置 OpenRouter 渠道 + model_mapping 即可,无需插件:
  - POST /v1/chat/completions      对话(路径透传)
  - POST /v1/rerank                重排        [已验证]
  - POST /v1/embeddings            向量        [已验证]
  - POST /v1/images/generations    生图        [已验证]
  - POST /v1/audio/speech          语音合成    [已验证]
  - POST /v1/audio/transcriptions  语音转写(multipart,未测)
  - POST /v1/responses             Responses(未测)
  - POST /v1/messages              会转 chat 格式打上游 /v1/chat/completions
  - GET  /v1/models                模型列表

【必须插件】网关没有入口路径或需要任务管线,走 plugins/openrouter/plugin.js:
  - POST /v1/alpha/decisions  → 上游 /api/alpha/decisions(TEST_PLUGIN=1 才测)
  - POST /v1/videos           → 异步视频任务(搁置中)

用法:
    set NEW_API_BASE=http://localhost:3000
    set NEW_API_KEY=sk-你的new-api令牌
    python verify.py

判定口径:
  - 200/正常返回         → 通过
  - 返回体里 model 为上游名 → 顺带验证 model_mapping 生效
  - 404 / 无可用渠道      → 网关路由或渠道选择问题(没到上游)
  - 上游风格 4xx          → 路由已通,参数/额度问题(OpenRouter 拒绝了)
"""

import json
import os
import sys
import urllib.request
import urllib.error

BASE = os.environ.get("NEW_API_BASE", "http://localhost:3000").rstrip("/")
KEY = os.environ.get("NEW_API_KEY", "")
TIMEOUT = 120

# 渠道里配置的下游别名 → 渠道 model_mapping 指向的上游模型
# 按你的截图填写(大小写与渠道模型列表完全一致),用于校验响应回显的模型名
EXPECTED_UPSTREAM = {
    "Rerank": "nvidia/llama-nemotron-rerank-vl-1b-v2:free",
    "Embed": "nvidia/nemotron-3-embed-1b:free",
    "Speech": "fish-audio/s2.1-pro-free:free",
    "Decisions": "parallel/decisions-fast:free",
    "Image": "",  # 换成你映射的图像模型,如 openai/gpt-5-image-mini
}


def post(path, body, timeout=TIMEOUT):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + KEY,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) newapi-verify/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            return resp.status, ctype, raw
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()
    except Exception as e:
        return 0, "", str(e).encode()


def check_model_echo(alias, payload):
    """响应体里如果带 model 字段,核对是不是映射后的上游名。
    OpenRouter 可能回显它内部的模型 id(如 private/openrouter/vendor/name),
    只要回显值含有映射名去掉 :free 等修饰后的主体就算映射生效。"""
    echoed = payload.get("model") if isinstance(payload, dict) else None
    if not echoed:
        return "  (响应未回显 model,跳过映射校验)"
    want = EXPECTED_UPSTREAM.get(alias, "")
    core = want.split(":")[0].split("/")[-1]
    if echoed == alias:
        return "  !! 回显 model=%r 仍是别名 —— model_mapping 没生效" % echoed
    if core and core in echoed:
        return "  回显 model=%r ✓ 映射生效" % echoed
    return "  回显 model=%r(期望包含 %r,人工确认)" % (echoed, core or want)


def report(name, ok, detail=""):
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))
    return ok


def run(name, alias, path, body, check=None):
    status, ctype, raw = post(path, body)
    if status == 200:
        if "application/json" in ctype:
            payload = json.loads(raw)
            detail = check_model_echo(alias, payload)
            extra = check(payload) if check else ""
            return report(name, True, extra + detail)
        if "text/html" in ctype:
            # SPA 页面 fallback:路由没注册时网关会把请求交给前端页面
            return report(name, False, "返回的是前端 HTML,说明该入口没有注册(插件路由未生效)")
        return report(name, True, "二进制响应 %d 字节, Content-Type=%s" % (len(raw), ctype))
    text = raw.decode(errors="replace")[:300]
    if status == 0:
        return report(name, False, "连不上 new-api: " + text)
    if status == 404 or "无可用渠道" in text or "no available channel" in text.lower():
        return report(name, False, "路由未注册或渠道未选中(没到上游): " + text)
    # 上游风格的错误:说明路由已通,是 OpenRouter 侧拒绝
    if status in (400, 401, 402, 403, 404, 422, 429, 500, 503):
        return report(name, False, "已到上游但被拒绝(路由通,检查参数/额度/上游模型): %d %s" % (status, text))
    return report(name, False, "HTTP %d: %s" % (status, text))


def main():
    if not KEY:
        print("先设置 NEW_API_KEY 环境变量(new-api 的下游令牌)")
        sys.exit(1)
    print("目标 new-api:", BASE)
    results = []

    # 1. Rerank(正确路径透传)
    results.append(run(
        "rerank POST /v1/rerank           model=Rerank",
        "Rerank", "/v1/rerank",
        {"model": "Rerank", "query": "apple",
         "documents": ["banana is a fruit", "apple pie recipe", "stock market news"],
         "top_n": 2},
        check=lambda p: "results=%d" % len(p.get("results", [])),
    ))

    # 2. Embeddings
    results.append(run(
        "embed  POST /v1/embeddings       model=Embed",
        "Embed", "/v1/embeddings",
        {"model": "Embed", "input": "hello world"},
        check=lambda p: "dim=%d" % len(p["data"][0]["embedding"]) if p.get("data") else "no data",
    ))

    # 3. 图像生成(返回 b64 存 image_out.png,返回 url 下载;size/quality 按上游模型要求调)
    status, ctype, raw = post("/v1/images/generations", {
        "model": "Image", "prompt": "a cat sitting on a windowsill",
        "size": "1024x1024", "n": 1,
    }, timeout=300)
    image_ok, image_detail = False, ""
    if status == 200 and "application/json" in ctype:
        data = json.loads(raw).get("data") or []
        first = data[0] if data else {}
        if first.get("b64_json"):
            import base64
            blob = base64.b64decode(first["b64_json"])
            with open("image_out.png", "wb") as f:
                f.write(blob)
            image_ok, image_detail = True, "已存 image_out.png (%d 字节 b64)" % len(blob)
        elif first.get("url"):
            try:
                with urllib.request.urlopen(first["url"], timeout=120) as r:
                    blob = r.read()
                with open("image_out.png", "wb") as f:
                    f.write(blob)
                image_ok, image_detail = True, "已存 image_out.png (%d 字节,来自url)" % len(blob)
            except Exception as e:
                image_detail = "下载图片失败: " + str(e)
        else:
            image_detail = "响应无 b64_json/url"
    else:
        image_detail = "HTTP %s: %s" % (status, raw.decode(errors="replace")[:300])
    results.append(report("image  POST /v1/images/generations model=Image", image_ok, image_detail))

    # 4. Speech(返回音频二进制;voice 取值看上游 fish-audio 模型要求)
    status, ctype, raw = post("/v1/audio/speech", {
        "model": "Speech", "input": "Hello from new-api", "voice": "alloy",
    })
    if status == 200 and len(raw) > 100:
        with open("speech_out.mp3", "wb") as f:
            f.write(raw)
        results.append(report("speech POST /v1/audio/speech       model=Speech", True,
                              "已存 speech_out.mp3 (%d 字节, %s)" % (len(raw), ctype)))
    else:
        results.append(report("speech POST /v1/audio/speech       model=Speech", False,
                              "HTTP %s: %s" % (status, raw.decode(errors="replace")[:300])))

    # 5. Decisions 模型走 chat 入口的探针:若上游接受 messages 格式,
    #    文本类决策直接走 /v1/chat/completions 即可,不需要插件端点
    results.append(run(
        "decis  POST /v1/chat/completions model=Decisions (chat探针)",
        "Decisions", "/v1/chat/completions",
        {"model": "Decisions",
         "messages": [{"role": "user", "content": "Answer yes or no: is the sky blue?"}],
         "max_tokens": 32},
        check=lambda p: "choices=%d(上游接受chat格式,文本决策可直接用)" % len(p.get("choices", [])),
    ))

    # 6-7. Decisions 结构化接口(questions/state)依赖插件原生路由,
    #      未上传插件时必然 404(前端 HTML fallback)。
    #      上传并启用插件渠道后设 TEST_PLUGIN=1 再验证这两条。
    if os.environ.get("TEST_PLUGIN") == "1":
        results.append(run(
            "decis  POST /v1/alpha/decisions  model=Decisions",
            "Decisions", "/v1/alpha/decisions",
            {"model": "Decisions",
             "state": "Customer ticket: my corporate card was declined (ERR_CARD_DECLINED) "
                      "while upgrading to Team tier; invoice now overdue.",
             "questions": {
                 "department": {"type": "choice",
                                "instructions": "Which department should handle this ticket?",
                                "criteria": {
                                    "billing": "Invoices, card charges, upgrades, payment issues",
                                    "technical_support": "API bugs, latency, SDK crashes",
                                    "sales": "Enterprise contracts, volume pricing"}},
                 "is_churn_risk": {"type": "noul",
                                   "instructions": "Is this customer expressing intent to cancel?"},
             }},
        ))
        results.append(run(
            "decis  POST /openrouter/v1/alpha/decisions (前缀副本)",
            "Decisions", "/openrouter/v1/alpha/decisions",
            {"model": "Decisions",
             "state": "Is the sky blue?",
             "questions": {"sky_blue": {"type": "noul", "instructions": "Is the sky blue?"}}},
        ))
    else:
        print("  [SKIP] decisions 两条(插件未上传;设 TEST_PLUGIN=1 启用)")

    print()
    ok = sum(results)
    print("结果: %d/%d 通过" % (ok, len(results)))
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
