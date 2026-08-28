# -*- coding: utf-8 -*-
"""大模型能力（OpenAI 兼容 /chat/completions）。"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
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

    def _api_key(self, profile: dict[str, Any] | None = None) -> str:
        from services.integrations.secrets import get_profile_secret, get_secret

        if profile:
            cap = str(profile.get("capability") or "text_llm")
            pid = str(profile.get("id") or "")
            key = get_profile_secret(cap, pid, "api_key")
            if key:
                return key
            if pid and pid != "moonshot_kimi":
                api_base = str(profile.get("api_base") or "").lower()
                if "deepseek" in api_base:
                    val = os.environ.get("DEEPSEEK_API_KEY")
                    return str(val).strip() if val else ""
                if "moonshot" in api_base:
                    val = os.environ.get("MOONSHOT_API_KEY")
                    return str(val).strip() if val else ""
                return ""
        return str(
            get_secret("llm", "api_key")
            or self._config.get("api_key")
            or os.environ.get("TOA_LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()

    def _merge_profile(self, profile_id: str | None) -> dict[str, Any]:
        from services.model_catalog import resolve_text_llm_profile

        try:
            prof = resolve_text_llm_profile(profile_id)
        except KeyError:
            prof = {}
        merged = dict(self._config)
        for k in (
            "provider",
            "api_base",
            "model",
            "temperature",
            "model_fallbacks",
            "timeout_seconds",
        ):
            if prof.get(k) is not None:
                merged[k] = prof[k]
        merged["_profile"] = prof
        return merged

    def _candidate_models(self, preferred: str, cfg: dict[str, Any]) -> list[str]:
        raw = cfg.get("model_fallbacks") or []
        extras = [str(x).strip() for x in raw if str(x).strip()] if isinstance(raw, list) else []
        out: list[str] = []
        for m in (preferred, *extras):
            if m and m not in out:
                out.append(m)
        # 仅当未配置任何回退且首选为空时，才用内置回退
        if not out:
            for m in _DEFAULT_FALLBACKS:
                if m not in out:
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
        cfg = self._merge_profile(kwargs.get("profile_id"))
        profile = cfg.get("_profile") or {}
        api_base = str(cfg.get("api_base") or "").strip().rstrip("/")
        if not api_base:
            raise self.integration_error(
                "llm.api_base 未配置",
                user_message=(
                    "大模型尚未配置：请在「系统设置 → 能力接入 → 大模型」选择或添加模型配置，"
                    "并保存 API Key（写入本机 data/user，不进仓库）。"
                ),
            )

        preferred = str(kwargs.get("model") or cfg.get("model") or "kimi-k2.6").strip()
        temperature = float(kwargs.get("temperature", cfg.get("temperature", 0.7)))
        if preferred.startswith("kimi-k2"):
            temperature = 1.0
        url = urljoin(api_base + "/", "chat/completions")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        prof_dict = profile if isinstance(profile, dict) else {}
        key = self._api_key(prof_dict or None)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        elif prof_dict.get("id") and str(prof_dict.get("api_base") or "").strip():
            api_base = str(prof_dict.get("api_base") or "").lower()
            if "127.0.0.1" not in api_base and "localhost" not in api_base and not key:
                label = str(prof_dict.get("label") or prof_dict.get("id") or "当前模型")
                raise self.integration_error(
                    "profile api_key missing",
                    user_message=(
                        f"「{label}」尚未配置 API Key。"
                        "请在「系统设置 → 能力接入 → 大模型」选中该配置并保存 Key；"
                        "Moonshot 与 DeepSeek 密钥不能混用。"
                    ),
                )

        last_err: Exception | None = None
        for model in self._candidate_models(preferred, cfg):
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

    def complete_stream(
        self,
        prompt: str,
        *,
        system: str = "",
        **kwargs: Any,
    ) -> Iterator[str]:
        """流式输出文本增量；失败时抛出 IntegrationError。"""
        self.require_enabled()
        cfg = self._merge_profile(kwargs.get("profile_id"))
        profile = cfg.get("_profile") or {}
        api_base = str(cfg.get("api_base") or "").strip().rstrip("/")
        if not api_base:
            raise self.integration_error(
                "llm.api_base 未配置",
                user_message=(
                    "大模型尚未配置：请在「系统设置 → 能力接入 → 大模型」选择或添加模型配置，"
                    "并保存 API Key（写入本机 data/user，不进仓库）。"
                ),
            )

        preferred = str(kwargs.get("model") or cfg.get("model") or "kimi-k2.6").strip()
        temperature = float(kwargs.get("temperature", cfg.get("temperature", 0.7)))
        if preferred.startswith("kimi-k2"):
            temperature = 1.0
        url = urljoin(api_base + "/", "chat/completions")
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        prof_dict = profile if isinstance(profile, dict) else {}
        key = self._api_key(prof_dict or None)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        elif prof_dict.get("id") and str(prof_dict.get("api_base") or "").strip():
            api_base_lower = str(prof_dict.get("api_base") or "").lower()
            if (
                "127.0.0.1" not in api_base_lower
                and "localhost" not in api_base_lower
                and not key
            ):
                label = str(prof_dict.get("label") or prof_dict.get("id") or "当前模型")
                raise self.integration_error(
                    "profile api_key missing",
                    user_message=(
                        f"「{label}」尚未配置 API Key。"
                        "请在「系统设置 → 能力接入 → 大模型」选中该配置并保存 Key；"
                        "Moonshot 与 DeepSeek 密钥不能混用。"
                    ),
                )

        last_err: Exception | None = None
        for model in self._candidate_models(preferred, cfg):
            try:
                for chunk in self._iter_complete_stream(
                    url,
                    headers,
                    model=model,
                    prompt=str(prompt or ""),
                    system=system,
                    temperature=temperature,
                ):
                    yield chunk
                if model != preferred:
                    logger.info("LLM 流式使用回退模型 %s（配置为 %s）", model, preferred)
                return
            except Exception as exc:
                last_err = exc
                detail = str(exc)
                if "429" in detail or "限流" in detail:
                    raise
                if any(
                    x in detail
                    for x in ("404", "400", "not_found", "Not found", "invalid_model", "model")
                ):
                    logger.info("LLM 流式模型 %s 失败，尝试回退：%s", model, detail[:160])
                    continue
                # 不支持流式时整段返回
                if "stream" in detail.lower() or "event-stream" in detail.lower():
                    text = self.complete(
                        prompt,
                        system=system,
                        profile_id=kwargs.get("profile_id"),
                        model=model,
                        temperature=temperature,
                    )
                    if text:
                        yield text
                    return
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

    def _iter_complete_stream(
        self,
        url: str,
        headers: dict[str, str],
        *,
        model: str,
        prompt: str,
        system: str,
        temperature: float,
    ) -> Iterator[str]:
        try:
            yield from self._stream_request(
                url,
                self._chat_body(
                    model=model,
                    prompt=prompt,
                    system=system,
                    temperature=temperature,
                    merged=False,
                ),
                headers,
            )
        except Exception as first:
            detail = str(first)
            if system and ("400" in detail or "system" in detail.lower()):
                logger.info("LLM 流式 system 角色可能不受支持，改用合并 prompt 重试")
                yield from self._stream_request(
                    url,
                    self._chat_body(
                        model=model,
                        prompt=prompt,
                        system=system,
                        temperature=temperature,
                        merged=True,
                    ),
                    headers,
                )
                return
            raise

    def _chat_body(
        self,
        *,
        model: str,
        prompt: str,
        system: str,
        temperature: float,
        merged: bool,
    ) -> dict[str, Any]:
        if merged:
            content = prompt
            if system:
                content = f"{system.strip()}\n\n---\n\n{prompt}"
            messages: list[dict[str, str]] = [{"role": "user", "content": content}]
        else:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if model.startswith("kimi-k3"):
            body["reasoning_effort"] = "low"
        return body

    @staticmethod
    def _parse_sse_delta(line: str) -> str:
        raw = (line or "").strip()
        if not raw.startswith("data:"):
            return ""
        payload = raw[5:].strip()
        if not payload or payload == "[DONE]":
            return ""
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            return ""
        if isinstance(obj, dict) and obj.get("error"):
            err = obj.get("error")
            if isinstance(err, dict):
                raise ValueError(str(err.get("message") or err))
            raise ValueError(str(err))
        choices = obj.get("choices") or []
        if not choices:
            return ""
        choice = choices[0] if isinstance(choices[0], dict) else {}
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            return ""
        text = str(delta.get("content") or "")
        if text:
            return text
        return str(delta.get("reasoning_content") or "")

    def _stream_request(
        self,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
    ) -> Iterator[str]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        try:
            import httpx
        except ImportError:
            payload = self._post_json(url, {**body, "stream": False}, headers)
            text = self._extract_text(payload)
            if text:
                yield text
            return

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", url, content=data, headers=headers) as resp:
                    if resp.status_code >= 400:
                        raw = resp.read().decode("utf-8", errors="replace")
                        self._raise_http_error(resp.status_code, raw)
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        chunk = self._parse_sse_delta(line)
                        if chunk:
                            yield chunk
        except Exception as exc:
            if hasattr(exc, "service"):
                raise
            raise self.integration_error(
                str(exc),
                user_message=f"大模型流式请求失败：{exc}",
            ) from exc

    def _raise_http_error(self, status_code: int, raw: str) -> None:
        hint = raw[:220].replace("\n", " ")
        user = f"大模型请求失败（HTTP {status_code}）。"
        if status_code == 401:
            user += (
                " API Key 无效或与当前模型不匹配。"
                "请在「系统设置 → 能力接入」为当前所选配置单独保存 Key"
                "（Moonshot Key 不能用于 DeepSeek）。"
            )
        elif status_code in (400, 404) and (
            "model" in hint.lower() or "not found" in hint.lower()
        ):
            user += (
                " 模型名不可用：请在「系统设置 → 能力接入」改为 "
                "kimi-k2.6（Moonshot 国内站推荐），保存后再试。"
            )
        elif status_code == 429:
            raise self.integration_error(
                f"HTTP 429: {hint}",
                user_message=(
                    "大模型限流（请求过快或账号每分钟次数已满）。"
                    "请等待约 10 秒后再试，勿连续连点；或切换到「能力接入」里另一套模型配置。"
                ),
            )
        if hint:
            user += f" 详情：{hint}"
        raise self.integration_error(
            f"HTTP {status_code}: {raw[:300]}",
            user_message=user,
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
            return self._chat_body(
                model=model,
                prompt=prompt,
                system=system,
                temperature=temperature,
                merged=False,
            )

        def _merged() -> dict[str, Any]:
            body = self._chat_body(
                model=model,
                prompt=prompt,
                system=system,
                temperature=temperature,
                merged=True,
            )
            body.pop("stream", None)
            return body

        try:
            body = _with_system()
            body.pop("stream", None)
            return self._post_json(url, body, headers)
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
            # 限流：少次、长间隔，避免连打配额
            delays = (3.0,)
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
                        if resp.status_code == 401:
                            user += (
                                " API Key 无效或与当前模型不匹配。"
                                "请在「系统设置 → 能力接入」为当前所选配置单独保存 Key"
                                "（Moonshot Key 不能用于 DeepSeek）。"
                            )
                        elif resp.status_code in (400, 404) and (
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
                    "大模型限流（请求过快或账号每分钟次数已满）。"
                    "请等待约 10 秒后再试，勿连续连点；或切换到「能力接入」里另一套模型配置。"
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
            if e.code == 429:
                raise self.integration_error(
                    f"HTTP 429: {detail}",
                    user_message=(
                        "大模型限流（请求过快或账号每分钟次数已满）。"
                        "请等待约 10 秒后再试，勿连续连点；或切换到「能力接入」里另一套模型配置。"
                    ),
                ) from e
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
