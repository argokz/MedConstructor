import logging
import json
from typing import Any, AsyncIterator, List

import openai

try:
    from google import genai
except ImportError:  # pragma: no cover - depends on optional runtime package
    genai = None

from app.config import get_settings

logger = logging.getLogger(__name__)


class LLMRouter:
    def __init__(self):
        self.settings = get_settings()
        self.openai_client = (
            openai.AsyncOpenAI(api_key=self.settings.openai_api_key)
            if self.settings.openai_api_key
            else None
        )
        self.gemini_client = (
            genai.Client(api_key=self.settings.gemini_api_key)
            if genai and self.settings.gemini_api_key
            else None
        )

        self.openai_models = [m.strip() for m in self.settings.openai_models.split(",") if m.strip()]
        self.gemini_models = [m.strip() for m in self.settings.gemini_models.split(",") if m.strip()]

        self.active_openai_model = self.openai_models[0] if self.openai_models else None
        self.active_gemini_model = self.gemini_models[0] if self.gemini_models else None
        self.active_provider = self.settings.primary_llm_provider

    async def get_embedding(self, text: str) -> List[float]:
        embedding_model = self.settings.embedding_model_name

        if "gemini" in embedding_model or "embedding-0" in embedding_model:
            if not self.gemini_client:
                raise ValueError("Gemini client not configured for embeddings")
            response = await self.gemini_client.aio.models.embed_content(
                model=embedding_model,
                contents=text,
            )
            return response.embeddings[0].values

        if not self.openai_client:
            raise ValueError("OpenAI client not configured for embeddings")
        response = await self.openai_client.embeddings.create(
            model=embedding_model,
            input=text,
        )
        return response.data[0].embedding

    async def chat_completion(self, prompt: str) -> str:
        return await self.chat_completion_messages(system_prompt=None, user_prompt=prompt)

    async def chat_completion_messages(
        self,
        user_prompt: str,
        system_prompt: str | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        providers_to_try = []
        if response_format and self.openai_client:
            providers_to_try.append("openai")
        providers_to_try.append(self.active_provider)
        other_provider = "openai" if self.active_provider == "gemini" else "gemini"
        providers_to_try.append(other_provider)
        providers_to_try = list(dict.fromkeys(providers_to_try))

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        for provider in providers_to_try:
            if provider == "gemini" and self.gemini_client and self.gemini_models:
                models_to_test = [self.active_gemini_model] + [
                    m for m in self.gemini_models if m != self.active_gemini_model
                ]
                for model in models_to_test:
                    try:
                        logger.info("Attempting Gemini model: %s", model)
                        full_prompt = (
                            f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
                        )
                        if response_format:
                            schema = response_format.get("json_schema", {}).get("schema", {})
                            full_prompt += (
                                "\n\nReturn only valid JSON matching this JSON Schema:\n"
                                + json.dumps(schema, ensure_ascii=False)
                            )
                        response = await self.gemini_client.aio.models.generate_content(
                            model=model,
                            contents=full_prompt,
                        )
                        self.active_gemini_model = model
                        self.active_provider = "gemini"
                        return response.text
                    except Exception as e:
                        logger.warning("Model %s failed: %s", model, str(e))
                        continue

            elif provider == "openai" and self.openai_client and self.openai_models:
                models_to_test = [self.active_openai_model] + [
                    m for m in self.openai_models if m != self.active_openai_model
                ]
                for model in models_to_test:
                    if "embedding" in model.lower():
                        continue
                    try:
                        logger.info("Attempting OpenAI model: %s", model)
                        kwargs: dict[str, Any] = {
                            "model": model,
                            "messages": messages,
                        }
                        if response_format:
                            kwargs["response_format"] = response_format
                        response = await self.openai_client.chat.completions.create(
                            **kwargs,
                        )
                        self.active_openai_model = model
                        self.active_provider = "openai"
                        return response.choices[0].message.content or ""
                    except Exception as e:
                        logger.warning("Model %s failed: %s", model, str(e))
                        continue

        raise RuntimeError("All configured LLM providers and models failed.")

    async def chat_completion_json_schema(
        self,
        *,
        name: str,
        schema: dict[str, Any],
        user_prompt: str,
        system_prompt: str | None = None,
        strict: bool = True,
    ) -> str:
        return await self.chat_completion_messages(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": name,
                    "strict": strict,
                    "schema": schema,
                },
            },
        )

    async def chat_completion_stream(
        self,
        user_prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if not self.openai_client or not self.openai_models:
            text = await self.chat_completion_messages(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
            )
            yield text
            return

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        model = self.active_openai_model or self.openai_models[0]
        if "embedding" in model.lower():
            model = next((m for m in self.openai_models if "embedding" not in m.lower()), model)

        stream = await self.openai_client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


llm_router = LLMRouter()
