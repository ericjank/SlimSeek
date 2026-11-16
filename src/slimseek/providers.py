from abc import ABC, abstractmethod
from typing import Any

import httpx

from .config import Settings
from .errors import ProviderError


class ModelProvider(ABC):
    def __init__(self, timeout: float):
        self.timeout = timeout

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        pass

    @abstractmethod
    async def chat(self, system: str, user: str) -> str:
        pass

    async def _post(
        self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise ProviderError("模型服务响应超时，请检查服务状态或调大超时时间") from None
        except httpx.HTTPError:
            raise ProviderError("无法连接模型服务，请检查 Base URL 和服务运行状态") from None

        if response.status_code >= 400:
            raise ProviderError(f"模型服务请求失败（HTTP {response.status_code}），请检查模型名和配置")
        try:
            value = response.json()
        except ValueError:
            raise ProviderError("模型服务返回了无效的 JSON 响应") from None
        if not isinstance(value, dict):
            raise ProviderError("模型服务返回了无法识别的响应")
        return value


class OpenAIProvider(ModelProvider):
    def __init__(self, settings: Settings):
        super().__init__(settings.request_timeout_seconds)
        self.base_url = settings.openai_base_url.rstrip("/")
        self.embedding_model = settings.openai_embedding_model
        self.chat_model = settings.openai_chat_model
        self.headers = {}
        if settings.openai_api_key:
            self.headers["Authorization"] = f"Bearer {settings.openai_api_key}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload = await self._post(
            f"{self.base_url}/embeddings",
            {"model": self.embedding_model, "input": texts},
            self.headers,
        )
        try:
            data = payload["data"]
            ordered = sorted(data, key=lambda item: item["index"])
            vectors = [item["embedding"] for item in ordered]
            if len(vectors) != len(texts):
                raise ValueError
            return vectors
        except (KeyError, TypeError, ValueError):
            raise ProviderError("OpenAI 兼容接口返回了无效的嵌入数据") from None

    async def chat(self, system: str, user: str) -> str:
        payload = await self._post(
            f"{self.base_url}/chat/completions",
            {
                "model": self.chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
            },
            self.headers,
        )
        try:
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError
            return content.strip()
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("OpenAI 兼容接口返回了无效的回答数据") from None


class OllamaProvider(ModelProvider):
    def __init__(self, settings: Settings):
        super().__init__(settings.request_timeout_seconds)
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.embedding_model = settings.ollama_embedding_model
        self.chat_model = settings.ollama_chat_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload = await self._post(
            f"{self.base_url}/api/embed",
            {"model": self.embedding_model, "input": texts},
        )
        try:
            vectors = payload["embeddings"]
            if not isinstance(vectors, list) or len(vectors) != len(texts):
                raise ValueError
            return vectors
        except (KeyError, TypeError, ValueError):
            raise ProviderError("Ollama 返回了无效的嵌入数据，请使用支持 /api/embed 的版本") from None

    async def chat(self, system: str, user: str) -> str:
        payload = await self._post(
            f"{self.base_url}/api/chat",
            {
                "model": self.chat_model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "options": {"temperature": 0.1},
            },
        )
        try:
            content = payload["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError
            return content.strip()
        except (KeyError, TypeError, ValueError):
            raise ProviderError("Ollama 返回了无效的回答数据") from None


def create_provider(settings: Settings) -> ModelProvider:
    if settings.provider == "openai":
        return OpenAIProvider(settings)
    return OllamaProvider(settings)
