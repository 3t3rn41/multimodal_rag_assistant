"""Read-only environment models; credentials never enter the user database."""

import asyncio
import os
from urllib.parse import urlsplit

import httpx

from backend.core.errors import ServiceError
from backend.core.security.model_endpoints import validate_endpoint
from backend.infrastructure.jina.configuration import configuration_status, is_configured
from backend.infrastructure.jina.embedding import provider_http_error
from rag_engine.llm import OpenAICompatibleConfig


def environment_values(env=None):
    values = os.environ if env is None else env
    return {
        "llm_base_url": (values.get("RAG_LLM_BASE_URL") or "https://api.openai.com/v1").strip(),
        "llm_model": (values.get("RAG_LLM_MODEL") or values.get("OPENAI_MODEL") or "").strip(),
        "api_key": (values.get("RAG_LLM_API_KEY") or values.get("OPENAI_API_KEY") or "").strip(),
    }


def public_config(env=None):
    values = environment_values(env)
    key_configured = is_configured(values.pop("api_key"))
    missing = ([] if key_configured else ["RAG_LLM_API_KEY"]) + (
        [] if is_configured(values["llm_model"]) else ["RAG_LLM_MODEL"]
    )
    # Never echo an invalid URL that could contain a password or token.
    try:
        values["llm_base_url"] = validate_endpoint(values["llm_base_url"], env=env)
    except ServiceError:
        values["llm_base_url"] = ""
        missing.append("RAG_LLM_BASE_URL")
    return {
        **values, "llm_key_configured": key_configured,
        "configured": not missing, "missing": missing, "readonly": True,
        "configuration_source": "environment", "system_models": configuration_status(env),
    }


class ModelSettingsService:
    async def get(self):
        return public_config()

    async def answer_configuration(self):
        cfg = public_config()
        if not cfg["configured"]:
            raise ServiceError(
                "问答模型尚未就绪，请由管理员在项目 .env 配置 "
                + "、".join(cfg["missing"]) + " 并重启后端和 Worker。", 503
            )
        values = environment_values()
        url = await asyncio.to_thread(validate_endpoint, values["llm_base_url"], resolve=True)
        return OpenAICompatibleConfig(values["api_key"], values["llm_model"], url, 90)

    async def test(self):
        config = await self.answer_configuration()
        payload = {
            "model": config.model,
            "messages": [{"role": "user", "content": "Reply OK."}],
            "stream": False, "max_tokens": 256,
        }
        if (urlsplit(config.base_url).hostname == "maas.qianwenaiapi.com"
                and config.model.startswith("deepseek-v4")):
            payload["enable_thinking"] = False
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                response = await client.post(
                    config.base_url + "/chat/completions", json=payload,
                    headers={"Authorization": f"Bearer {config.api_key}"},
                )
                response.raise_for_status()
                data = response.json()
            if (not isinstance(data, dict) or not isinstance(data.get("choices"), list)
                    or not data["choices"]):
                raise ValueError()
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                if data["choices"][0].get("finish_reason") == "length":
                    raise ServiceError("已连接模型服务，但测试输出被截断，未收到正式回答。请检查模型输出配置。", 502)
                raise ValueError()
        except httpx.HTTPError as exc:
            raise ServiceError(str(provider_http_error(exc)), 502) from None
        except (ValueError, TypeError, KeyError, IndexError):
            raise ServiceError("模型服务返回格式无效或没有正式回答，请核对兼容接口和模型名称。", 502) from None
        return {"success": True, "message": "真实请求已成功，模型服务连接正常。"}
