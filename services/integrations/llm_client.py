# -*- coding: utf-8 -*-
"""大模型能力（OpenAI 兼容 /chat/completions）。"""
from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import urljoin

from services.integrations.base import IntegrationClient
from services.integrations.config import integration_config

logger = logging.getLogger(__name__)

# 国内 Moonshot 常见可用模型（新账号常无 moonshot-v1-*）
_DEFAULT_FALLBACKS = ("kimi-k2.6", "kimi-k2.5", "moonshot-v1-8k", "kimi-k3")


class LlmClient(IntegrationClient):
    name = "llm"

    def __init__(self) -> None:
        super().__init__(integration_config("llm"))

    def health_check(self) -> bool:
        if not self.enabled:
            return False
        return bool(str(self._config.get("api_base") or "").strip())

    def _api_key(self) -> str:
        from services.integrations.secrets import get_secret

        return str(
            get_secret("llm", "api_key")
            or self._config.get("api_key")
            or os.environ.get("TOA_LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()

    def _candidate_models(self, preferred: str) -> list[str]:
        raw = self._config.get("model_fallbacks") or []
        extras = [str(x).strip() for x in raw if str(x).strip()] if isinstance(raw, list) else []
        out: list[str] = []
        for m in (preferred, *extras, *_DEFAULT_FALLBACKS):
            if m and m not in out:
                out.append(m)
        return out

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise KeyError("choices")
        msg = choices[0].get("message") or {}
        text = str(msg.get("content") or "").strip()
        if text:
            return text
        # 思考模型偶发只回 reasoning_content
        reasoning = str(msg.get("reasoning_content") or "").strip()
        if reasoning:
            return reasoning
        raise ValueError("空回复")

    def complete(self, prompt: str, *, system: str = "", **kwargs: Any) -> str:
        self.require_enabled()
        api_base = str(self._config.get("api_base") or "").strip().rstrip("/")
        if not api_base:
            raise self.integration_error(
                "llm.api_base 未配置",
                user_message=(
                    "大模型尚未配置：请在「系统设置 → 能力接入」填写 API 地址 / 模型，"
                    "并保存 API Key（写入本机 data/user，不进仓库）。"
                ),
            )

        preferred = str(kwargs.get("model") or self._config.get("model") or "kimi-k2.6").strip()
        temperature = float(kwargs.get("temperature", self._config.get("temperature", 0.7)))
        url = urljoin(api_base + "/", "chat/completions")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        key = self._api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"

        last_err: Exception | None = None
        for model in self._candidate_models(preferred):
            try:
                payload = self._try_complete(
                    url,
                    headers,
                    model=model,
                    prompt=str(prompt or ""),
                    system=system,
                    temperature=temperature,
                )
                text = self._extract_text(payload)
                if model != preferred:
                    logger.info("LLM 使用回退模型 %s（配置为 %s）", model, preferred)
                return text
            except Exception as exc:
                last_err = exc
                detail = str(exc)
                # 限流：立刻失败，勿再换模型连打配额
                if "429" in detail or "限流" in detail:
                    raise
                # 模型不存在 / 无权限 → 试下一个
                if any(x in detail for x in ("404", "400", "not_found", "Not found", "invalid_model", "model")):
                    logger.info("LLM 模型 %s 失败，尝试回退：%s", model, detail[:160])
                    continue
                raise

        if last_err is not None:
            raise last_err
        raise self.integration_error(
            "无可用模型",
            user_message=(
                "大模型请求失败：请到「系统设置 → 能力接入」把模型改为 "
                "kimi-k2.6（Moonshot 国内站当前推荐），并确认 API Key 有效。"
            ),
        )

    def _try_complete(
        self,
        url: str,
        headers: dict[str, str],
        *,
        model: str,
        prompt: str,
        system: str,
        temperature: float,
    ) -> dict[str, Any]:
        def _with_system() -> dict[str, Any]:
            messages: list[dict[str, str]] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            body: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            # kimi-k3 需 reasoning_effort；过低成本翻译用 low
            if model.startswith("kimi-k3"):
                body["reasoning_effort"] = "low"
            return body

        def _merged() -> dict[str, Any]:
            content = prompt
            if system:
                content = f"{system.strip()}\n\n---\n\n{prompt}"
            body: dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": content}],
                "temperature": temperature,
            }
            if model.startswith("kimi-k3"):
                body["reasoning_effort"] = "low"
            return body

        try:
            return self._post_json(url, _with_system(), headers)
        except Exception as first:
            detail = str(first)
            if system and ("400" in detail or "system" in detail.lower()):
                logger.info("LLM system 角色可能不受支持，改用合并 prompt 重试")
                return self._post_json(url, _merged(), headers)
            raise

    def _post_json(self, url: str, body: dict, headers: dict[str, str]) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        try:
            import time

            import httpx

            last_detail = ""
            # 限流：少次、长间隔，避免连打把配额打光
            delays = (2.0, 4.0)
            for attempt, delay in enumerate(delays):
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, content=data, headers=headers)
                    raw = resp.text
                    if resp.status_code == 429:
                        last_detail = raw[:220].replace("\n", " ")
                        # 尊重 Retry-After（秒）
                        ra = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
                        wait = delay
                        if ra:
                            try:
                                wait = max(delay, float(ra))
                            except ValueError:
                                wait = delay
                        logger.info("LLM 429，%.1fs 后重试 (%s/%s)", wait, attempt + 1, len(delays))
                        time.sleep(wait)
                        continue
                    if resp.status_code >= 400:
                        hint = raw[:220].replace("\n", " ")
                        user = f"大模型请求失败（HTTP {resp.status_code}）。"
                        if resp.status_code in (400, 404) and (
                            "model" in hint.lower() or "not found" in hint.lower()
                        ):
                            user += (
                                " 模型名不可用：请在「系统设置 → 能力接入」改为 "
                                "kimi-k2.6（Moonshot 国内站推荐），保存后再试。"
                            )
                        if hint:
                            user += f" 详情：{hint}"
                        raise self.integration_error(
                            f"HTTP {resp.status_code}: {raw[:300]}",
                            user_message=user,
                        )
                    return json.loads(raw) if raw else {}
            raise self.integration_error(
                f"HTTP 429: {last_detail}",
                user_message=(
                    "大模型限流（账号每分钟次数用尽）。"
                    "请等待约 10 秒后再点「翻译原文」，勿连续连点。"
                ),
            )
        except ImportError:
            pass
        except Exception as exc:
            if hasattr(exc, "service"):  # IntegrationError
                raise
            raise self.integration_error(
                str(exc),
                user_message=f"大模型请求失败：{exc}",
            ) from exc

        import urllib.error
        import urllib.request

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            raise self.integration_error(
                f"HTTP {e.code}: {detail}",
                user_message=(
                    f"大模型请求失败（HTTP {e.code}）。"
                    " 若提示模型不存在，请改为 kimi-k2.6。"
                ),
            ) from e
        except Exception as exc:
            raise self.integration_error(
                str(exc),
                user_message=f"大模型请求失败：{exc}",
            ) from exc
