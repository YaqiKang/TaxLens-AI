from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class LLMProviderError(RuntimeError):
    """Base error kept inside the optional semantic-assistance boundary."""


class LLMUnavailableError(LLMProviderError):
    pass


class LLMTimeoutError(LLMProviderError):
    pass


class LLMInvalidOutputError(LLMProviderError):
    pass


class StructuredLLMProvider(Protocol):
    status: str

    def generate_json(
        self,
        *,
        task: str,
        system_prompt: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


@dataclass
class DisabledLLMProvider:
    status: str = "disabled_no_api_key"

    def generate_json(self, **_: Any) -> dict[str, Any]:
        raise LLMUnavailableError("LLM未配置，已使用安全降级流程")


@dataclass
class OpenAICompatibleProvider:
    endpoint: str
    api_key: str
    model: str
    status: str = "configured"

    def generate_json(
        self,
        *,
        task: str,
        system_prompt: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        body = json.dumps({
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps({"task": task, "input": payload}, ensure_ascii=False)},
            ],
        }).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                envelope = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, socket.timeout) as exc:
            raise LLMTimeoutError("LLM调用超时") from exc
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise LLMUnavailableError("LLM调用不可用") from exc
        try:
            content = envelope["choices"][0]["message"]["content"]
            result = json.loads(content) if isinstance(content, str) else content
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMInvalidOutputError("LLM返回结构无效") from exc
        if not isinstance(result, dict):
            raise LLMInvalidOutputError("LLM返回必须是JSON对象")
        return result


def provider_from_env() -> StructuredLLMProvider:
    key = os.getenv("TAXLENS_LLM_API_KEY", "").strip()
    endpoint = os.getenv("TAXLENS_LLM_ENDPOINT", "").strip()
    model = os.getenv("TAXLENS_LLM_MODEL", "").strip()
    if not key or not endpoint or not model:
        return DisabledLLMProvider()
    return OpenAICompatibleProvider(endpoint=endpoint, api_key=key, model=model)


def timeout_from_env() -> float:
    raw = os.getenv("TAXLENS_LLM_TIMEOUT_SECONDS", "8").strip()
    try:
        return max(1.0, min(float(raw), 30.0))
    except ValueError:
        return 8.0
