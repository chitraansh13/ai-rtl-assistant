import json
import socket
import time
from urllib import error, request

from rtl_assistant.llm.base import LLMProvider
from rtl_assistant.models.llm import LLMResponse, LLMStatus


class OllamaProvider(LLMProvider):
    """LLM provider backed by the local Ollama HTTP API."""

    def __init__(
        self,
        model: str = "qwen2.5-coder:7b",
        base_url: str = "http://localhost:11434",
        timeout_seconds: int = 60,
    ) -> None:
        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, prompt: str) -> LLMResponse:
        """Send a non-streaming generation request to Ollama and return a typed result."""

        started_at = time.perf_counter()
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        endpoint = f"{self._base_url}/api/generate"
        req = request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self._timeout_seconds) as response:
                raw_bytes = response.read()
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            raw_text = raw_bytes.decode("utf-8")

            try:
                raw_response = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                return self._failure_response(
                    prompt=prompt,
                    duration_ms=duration_ms,
                    error_type="OLLAMA_INVALID_RESPONSE",
                    error_message=f"Failed to decode Ollama JSON response: {exc}",
                    response_text=raw_text,
                )

            if not isinstance(raw_response, dict):
                return self._failure_response(
                    prompt=prompt,
                    duration_ms=duration_ms,
                    error_type="OLLAMA_INVALID_RESPONSE",
                    error_message="Ollama response root must be a JSON object.",
                    raw_response={"value": raw_response},
                    response_text=raw_text,
                )

            response_text = str(raw_response.get("response", "") or "")
            if not response_text.strip():
                error_message = str(raw_response.get("error", "") or "").lower()
                if "not found" in error_message and "model" in error_message:
                    return self._failure_response(
                        prompt=prompt,
                        duration_ms=duration_ms,
                        error_type="MODEL_NOT_FOUND",
                        error_message=str(raw_response.get("error")),
                        raw_response=raw_response,
                        response_text=raw_text,
                    )
                return self._failure_response(
                    prompt=prompt,
                    duration_ms=duration_ms,
                    error_type="EMPTY_MODEL_RESPONSE",
                    error_message="Ollama returned an empty response field.",
                    raw_response=raw_response,
                    response_text=raw_text,
                )

            return LLMResponse(
                provider=self.provider_name,
                model=str(raw_response.get("model") or self._model),
                prompt=prompt,
                response_text=response_text,
                success=True,
                status=LLMStatus.SUCCESS,
                duration_ms=duration_ms,
                raw_response=raw_response,
                prompt_tokens=raw_response.get("prompt_eval_count"),
                completion_tokens=raw_response.get("eval_count"),
                total_duration_ns=raw_response.get("total_duration"),
            )
        except error.HTTPError as exc:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            response_text = ""
            raw_response = None
            try:
                raw_body = exc.read().decode("utf-8")
                response_text = raw_body
                parsed = json.loads(raw_body)
                if isinstance(parsed, dict):
                    raw_response = parsed
                    message = str(parsed.get("error") or f"HTTP {exc.code}: {exc.reason}")
                else:
                    message = f"HTTP {exc.code}: {exc.reason}"
            except Exception:
                message = f"HTTP {exc.code}: {exc.reason}"

            if exc.code == 404 and raw_response and "not found" in str(raw_response.get("error", "")).lower():
                return self._failure_response(
                    prompt=prompt,
                    duration_ms=duration_ms,
                    error_type="MODEL_NOT_FOUND",
                    error_message=message,
                    raw_response=raw_response,
                    response_text=response_text,
                )

            return self._failure_response(
                prompt=prompt,
                duration_ms=duration_ms,
                error_type="OLLAMA_HTTP_ERROR",
                error_message=message,
                raw_response=raw_response,
                response_text=response_text,
            )
        except (TimeoutError, socket.timeout) as exc:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            return self._failure_response(
                prompt=prompt,
                duration_ms=duration_ms,
                error_type="OLLAMA_TIMEOUT",
                error_message=f"Ollama request timed out: {exc}",
            )
        except error.URLError as exc:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            reason_text = str(exc.reason)
            if "timed out" in reason_text.lower():
                error_type = "OLLAMA_TIMEOUT"
            else:
                error_type = "OLLAMA_UNAVAILABLE"
            return self._failure_response(
                prompt=prompt,
                duration_ms=duration_ms,
                error_type=error_type,
                error_message=f"Ollama request failed: {reason_text}",
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            return self._failure_response(
                prompt=prompt,
                duration_ms=duration_ms,
                error_type="LLM_EXECUTION_ERROR",
                error_message=f"Unexpected provider execution error: {exc}",
            )

    def _failure_response(
        self,
        prompt: str,
        duration_ms: int | None,
        error_type: str,
        error_message: str,
        raw_response: dict | None = None,
        response_text: str = "",
    ) -> LLMResponse:
        """Construct a typed failure response."""

        return LLMResponse(
            provider=self.provider_name,
            model=self._model,
            prompt=prompt,
            response_text=response_text,
            success=False,
            status=LLMStatus.FAIL,
            duration_ms=duration_ms,
            error_type=error_type,
            error_message=error_message,
            raw_response=raw_response,
        )
