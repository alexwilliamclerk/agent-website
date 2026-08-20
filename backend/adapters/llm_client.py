"""
LLM 客户端（OpenAI 兼容接口）

配置文件：backend/llm_config.json
{
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "api_key": "sk-xxx",
    "temperature": 0.7,
    "trust_env": false
}

支持任意 OpenAI 兼容的 API 服务（DeepSeek / OpenAI / 阿里百炼 / 本地 vLLM 等），
只需修改 llm_config.json 即可切换。
"""

from __future__ import annotations

import json
import os
import re
import sys

import httpx
from openai import OpenAI

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "llm_config.json")

# 启动时打印 LLM 状态
_cfg = None
try:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
        _cfg = json.load(_f)
except Exception:
    pass
if _cfg and _cfg.get("api_key", ""):
    print(f"[LLM] 已配置: {_cfg.get('model')} @ {_cfg.get('base_url')}", flush=True)
else:
    print("[LLM] 未配置 API Key，Agent 将使用规则引擎模式", flush=True)


def _load_config() -> dict:
    """加载 LLM 配置文件，文件不存在或解析失败时返回空 dict"""
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _get_client() -> OpenAI:
    config = _load_config()
    api_key = config.get("api_key", "")
    base_url = config.get("base_url", "https://api.deepseek.com")
    if not api_key:
        raise RuntimeError("llm_config.json 中 api_key 未配置")
    # trust_env=false（默认）时直连、不走系统代理；true 时尊重系统代理（供 OpenAI 等需代理的 base_url 使用）
    trust_env = bool(config.get("trust_env", False))
    if not trust_env:
        return OpenAI(api_key=api_key, base_url=base_url, http_client=httpx.Client(trust_env=False))
    return OpenAI(api_key=api_key, base_url=base_url)


def chat(system_prompt: str, user_message: str, temperature: float | None = None) -> str:
    """调用 LLM，返回文本"""
    config = _load_config()
    if temperature is None:
        temperature = float(config.get("temperature", 0.7))
    model = config.get("model", "deepseek-chat")
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
        print(f"[LLM] OK {model} 返回 {len(content)} 字符", flush=True)
        return content
    except RuntimeError:
        raise
    except Exception as e:
        print(f"[LLM] 调用失败 ({model}): {e}", file=sys.stderr, flush=True)
        return ""


def chat_json(system_prompt: str, user_message: str) -> dict:
    """调用 LLM 并解析 JSON 返回，解析失败返回空 dict"""
    text = chat(system_prompt, user_message, temperature=0.3)
    if not text:
        return {}
    # 尝试提取 JSON（处理 LLM 可能包裹的 markdown 代码块或尾部多余文本）
    for start_marker, end_marker in [("```json", "```"), ("```", "```"), ("{", None)]:
        try:
            start = text.index(start_marker)
            if start_marker == "{":
                start = text.index("{", start)
        except ValueError:
            continue
        body_start = start + len(start_marker) if start_marker != "{" else start
        if end_marker:
            try:
                end = text.index(end_marker, body_start)
                candidate = text[body_start:end].strip()
            except ValueError:
                continue
        else:
            candidate = text[body_start:]
        # 用 JSONDecoder 逐对象解析，只取第一个完整 JSON
        import json as _json
        try:
            decoder = _json.JSONDecoder()
            obj, _ = decoder.raw_decode(candidate)
            if isinstance(obj, dict):
                return obj
        except _json.JSONDecodeError:
            continue
    # fallback: 正则提取
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        print(f"[LLM] JSON 解析失败，未找到 {{...}}", file=sys.stderr, flush=True)
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        print(f"[LLM] JSON 解析失败: {e}", file=sys.stderr, flush=True)
        return {}
