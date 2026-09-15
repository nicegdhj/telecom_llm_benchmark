import json
import time
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class ChatResult:
    status: str
    content: str
    attempts: int
    error: str = ""
    response: Optional[Any] = None
    reasoning_content: str = ""
    finish_reason: Optional[str] = None
    performance: Optional[Dict[str, Any]] = None


class PartialStreamError(Exception):
    def __init__(self, cause: Exception, result: ChatResult) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.result = result


def normalize_chat_url(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if not url:
        raise ValueError("base URL must not be empty")
    if url.endswith("/chat/completions"):
        return url
    return f"{url}/chat/completions"


class ChatClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 120,
        retries: int = 2,
        opener: Optional[Callable[..., Any]] = None,
        sleeper: Optional[Callable[[float], None]] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.api_key = api_key
        self.url = normalize_chat_url(base_url)
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleeper or time.sleep
        self._clock = clock or time.perf_counter
        self._stream_usage_enabled = True
        self._stream_usage_lock = threading.Lock()

    def complete(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> ChatResult:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        for attempt in range(1, self.retries + 2):
            response_data = None
            try:
                request = urllib.request.Request(
                    self.url,
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    method="POST",
                )
                with self._opener(request, timeout=self.timeout) as response:
                    raw_body = response.read().decode("utf-8", errors="replace")
                try:
                    response_data = json.loads(raw_body)
                except json.JSONDecodeError as exc:
                    response_data = self._sanitize_payload({"body": raw_body[:4000]})
                    raise ValueError("response body is not valid JSON") from exc
                response_data = self._sanitize_payload(response_data)
                content = response_data["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("empty choices[0].message.content")
                return ChatResult(
                    status="success",
                    content=content,
                    attempts=attempt,
                    response=response_data,
                )
            except Exception as exc:
                if isinstance(exc, urllib.error.HTTPError):
                    response_data = self._read_http_error(exc)
                if attempt > self.retries:
                    return ChatResult(
                        status="failed",
                        content="",
                        attempts=attempt,
                        error=self._safe_error(exc),
                        response=response_data,
                    )
                self._sleep(float(attempt))
        raise RuntimeError("unreachable")

    def complete_stream(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> ChatResult:
        for attempt in range(1, self.retries + 2):
            started = self._clock()
            response_data = None
            try:
                payload = self._stream_payload(prompt, max_tokens, temperature)
                request = self._request(payload)
                try:
                    response = self._opener(request, timeout=self.timeout)
                except urllib.error.HTTPError as exc:
                    disabled, error_response = self._stream_usage_error(exc)
                    if disabled:
                        started = self._clock()
                        payload = self._stream_payload(prompt, max_tokens, temperature)
                        request = self._request(payload)
                        response = self._opener(request, timeout=self.timeout)
                    else:
                        response_data = error_response
                        raise RuntimeError(f"HTTP {exc.code}: {exc.reason}") from exc
                with response:
                    result = self._consume_stream(response, started, attempt)
                return result
            except Exception as exc:
                if isinstance(exc, PartialStreamError):
                    if attempt > self.retries:
                        exc.result.attempts = attempt
                        exc.result.error = self._safe_error(exc.cause)
                        return exc.result
                    self._sleep(float(attempt))
                    continue
                if isinstance(exc, urllib.error.HTTPError):
                    response_data = self._read_http_error(exc)
                if attempt > self.retries:
                    return ChatResult(
                        status="failed",
                        content="",
                        attempts=attempt,
                        error=self._safe_error(exc),
                        response=response_data,
                    )
                self._sleep(float(attempt))
        raise RuntimeError("unreachable")

    def _stream_payload(self, prompt: str, max_tokens: int, temperature: float) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        with self._stream_usage_lock:
            if self._stream_usage_enabled:
                payload["stream_options"] = {"include_usage": True}
        return payload

    def _request(self, payload: Dict[str, Any]) -> urllib.request.Request:
        return urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

    def _consume_stream(self, response: Any, started: float, attempt: int) -> ChatResult:
        content_parts = []
        reasoning_parts = []
        usage = None
        finish_reason = None
        first_token_at = None
        first_answer_at = None
        non_sse_lines = []
        iterator = iter(response)
        while True:
            try:
                raw_line = next(iterator)
            except StopIteration:
                break
            except Exception as exc:
                raise self._partial_stream_error(
                    exc, started, first_token_at, first_answer_at,
                    content_parts, reasoning_parts, usage, finish_reason,
                ) from exc
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                non_sse_lines.append(line)
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = self._sanitize_payload(json.loads(data))
            except Exception as exc:
                raise self._partial_stream_error(
                    exc, started, first_token_at, first_answer_at,
                    content_parts, reasoning_parts, usage, finish_reason,
                ) from exc
            if chunk.get("usage") is not None:
                usage = chunk["usage"]
            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            delta = choice.get("delta") or {}
            reasoning = delta.get("reasoning_content") or ""
            content = delta.get("content") or ""
            event_time = self._clock() if reasoning or content else None
            if event_time is not None and first_token_at is None:
                first_token_at = event_time
            if content and first_answer_at is None:
                first_answer_at = event_time
            if reasoning:
                reasoning_parts.append(str(reasoning))
            if content:
                content_parts.append(str(content))
            if choice.get("finish_reason") is not None:
                finish_reason = choice["finish_reason"]
        if non_sse_lines and not content_parts and not reasoning_parts:
            return self._ordinary_stream_fallback(non_sse_lines, started, attempt)
        finished = self._clock()
        content = "".join(content_parts)
        reasoning_content = "".join(reasoning_parts)
        if not content.strip():
            exc = ValueError("empty streamed content")
            raise self._partial_stream_error(
                exc, started, first_token_at, first_answer_at,
                content_parts, reasoning_parts, usage, finish_reason,
                finished=finished,
            ) from exc
        performance = self._performance(
            started,
            finished,
            first_token_at,
            first_answer_at,
            usage,
            len(content) + len(reasoning_content),
        )
        reconstructed = self._sanitize_payload(
            {
                "stream": True,
                "content": content,
                "reasoning_content": reasoning_content,
                "finish_reason": finish_reason,
                "usage": usage,
            }
        )
        return ChatResult(
            status="success",
            content=content,
            attempts=attempt,
            response=reconstructed,
            reasoning_content=reasoning_content,
            finish_reason=finish_reason,
            performance=performance,
        )

    def _partial_stream_error(
        self,
        cause: Exception,
        started: float,
        first_token_at: Optional[float],
        first_answer_at: Optional[float],
        content_parts: list,
        reasoning_parts: list,
        usage: Optional[Dict[str, Any]],
        finish_reason: Optional[str],
        finished: Optional[float] = None,
    ) -> PartialStreamError:
        finished = self._clock() if finished is None else finished
        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts)
        performance = self._performance(
            started, finished, first_token_at, first_answer_at, usage,
            len(content) + len(reasoning),
        )
        response = self._sanitize_payload({
            "stream": True,
            "content": content,
            "reasoning_content": reasoning,
            "finish_reason": finish_reason,
            "usage": usage,
        })
        result = ChatResult(
            status="failed",
            content=content,
            attempts=0,
            response=response,
            reasoning_content=reasoning,
            finish_reason=finish_reason,
            performance=performance,
        )
        return PartialStreamError(cause, result)

    def _ordinary_stream_fallback(
        self,
        lines: list,
        started: float,
        attempt: int,
    ) -> ChatResult:
        payload = self._sanitize_payload(json.loads("\n".join(lines)))
        message = payload["choices"][0]["message"]
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""
        if not content.strip():
            raise ValueError("empty choices[0].message.content")
        finished = self._clock()
        performance = self._performance(
            started,
            finished,
            None,
            None,
            payload.get("usage"),
            len(content) + len(reasoning),
        )
        return ChatResult(
            status="success",
            content=content,
            attempts=attempt,
            response=payload,
            reasoning_content=reasoning,
            finish_reason=payload["choices"][0].get("finish_reason"),
            performance=performance,
        )

    def _performance(
        self,
        started: float,
        finished: float,
        first_token_at: Optional[float],
        first_answer_at: Optional[float],
        usage: Optional[Dict[str, Any]],
        output_chars: int,
    ) -> Dict[str, Any]:
        ttft = first_token_at - started if first_token_at is not None else None
        first_answer = first_answer_at - started if first_answer_at is not None else None
        total = finished - started
        generation = finished - first_token_at if first_token_at is not None else None
        completion_tokens = usage.get("completion_tokens") if usage else None
        tokens_per_second = None
        chars_per_second = None
        if generation is not None and generation > 0:
            if completion_tokens is not None:
                tokens_per_second = float(completion_tokens) / generation
            chars_per_second = output_chars / generation
        return {
            "ttft_seconds": _rounded(ttft),
            "first_answer_token_seconds": _rounded(first_answer),
            "total_latency_seconds": _rounded(total),
            "generation_seconds": _rounded(generation),
            "completion_tokens": completion_tokens,
            "tokens_per_second": _rounded(tokens_per_second),
            "output_chars": output_chars,
            "chars_per_second": _rounded(chars_per_second),
        }

    def _stream_usage_error(self, exc: urllib.error.HTTPError) -> tuple:
        response = self._read_http_error(exc)
        rendered = json.dumps(response, ensure_ascii=False)
        if exc.code not in (400, 422) or "stream_options" not in rendered:
            return False, response
        with self._stream_usage_lock:
            self._stream_usage_enabled = False
        return True, response

    def _safe_error(self, exc: Exception) -> str:
        message = f"{type(exc).__name__}: {exc}"
        if self.api_key:
            message = message.replace(self.api_key, "***")
        return message[:1000]

    def _read_http_error(self, exc: urllib.error.HTTPError) -> Any:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        finally:
            exc.close()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"status": exc.code, "body": body[:4000]}
        return self._sanitize_payload(payload)

    def _sanitize_payload(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            return {key: self._sanitize_payload(value) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self._sanitize_payload(value) for value in payload]
        if isinstance(payload, str) and self.api_key:
            return payload.replace(self.api_key, "***")
        return payload


def _rounded(value: Optional[float]) -> Optional[float]:
    return round(value, 4) if value is not None else None
