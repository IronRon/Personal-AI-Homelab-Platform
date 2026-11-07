
import json
import socket
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


@dataclass(frozen=True)
class OllamaChatResponse:
    """Final response and optional reasoning returned by Ollama."""

    content: str
    thinking: str = ""
    tool_calls: list = field(default_factory=list)


class OllamaError(Exception):
    """Base exception for Ollama integration errors."""


class OllamaConnectionError(OllamaError):
    """Raised when Django cannot connect to Ollama."""


class OllamaTimeoutError(OllamaError):
    """Raised when Ollama takes too long to respond."""


class OllamaHTTPError(OllamaError):
    """Raised when Ollama returns an HTTP error."""


class OllamaResponseError(OllamaError):
    """Raised when Ollama returns an invalid response."""


class OllamaService:
    """Handles communication between Django and local Ollama."""

    def __init__(self, base_url=None, model=None, timeout=None):
        self.base_url = (
            base_url or settings.OLLAMA_BASE_URL
        ).rstrip("/")

        self.model = model or settings.OLLAMA_MODEL

        self.timeout = (
            timeout
            if timeout is not None
            else settings.OLLAMA_TIMEOUT_SECONDS
        )

    def chat(self, message: str, history=None, tools=None) -> OllamaChatResponse:
        """Send a user message with optional history and Ollama tool definitions."""
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Message cannot be empty.")

        conversation = []
        if history is not None:
            if not isinstance(history, list):
                raise ValueError("Conversation history must be a list.")
            for item in history:
                if not isinstance(item, dict):
                    raise ValueError("Conversation history contains an invalid item.")
                role = item.get("role")
                content = item.get("content", "")
                if role not in ("user", "assistant", "tool") or not isinstance(content, str):
                    raise ValueError("Conversation history contains an invalid message.")
                message_item = {"role": role, "content": content}
                if role == "assistant" and isinstance(item.get("tool_calls"), list):
                    message_item["tool_calls"] = item["tool_calls"]
                conversation.append(message_item)

        conversation.append({"role": "user", "content": message.strip()})
        return self.chat_messages(conversation, tools=tools)

    def chat_messages(self, messages, tools=None) -> OllamaChatResponse:
        """Send a complete Ollama conversation, optionally enabling function tools."""
        if not isinstance(messages, list) or not messages:
            raise ValueError("At least one conversation message is required.")
        for item in messages:
            if not isinstance(item, dict) or item.get("role") not in ("system", "user", "assistant", "tool"):
                raise ValueError("Conversation contains an invalid message.")
            if not isinstance(item.get("content", ""), str):
                raise ValueError("Conversation message content must be text.")

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": settings.OLLAMA_THINK,
        }
        if tools:
            payload["tools"] = tools

        request = Request(
            url=f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                response_body = response.read()
        except HTTPError as exc:
            raise OllamaHTTPError(f"Ollama returned HTTP {exc.code}.") from exc
        except (socket.timeout, TimeoutError) as exc:
            raise OllamaTimeoutError("Ollama took too long to respond.") from exc
        except URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise OllamaTimeoutError("Ollama took too long to respond.") from exc
            raise OllamaConnectionError(
                "Could not connect to Ollama. Check that Ollama is running."
            ) from exc
        except OSError as exc:
            raise OllamaConnectionError(
                "Could not connect to Ollama. Check that Ollama is running."
            ) from exc

        try:
            data = json.loads(response_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as exc:
            raise OllamaResponseError("Ollama returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise OllamaResponseError("Ollama returned an unexpected response.")

        assistant_message = data.get("message")
        if not isinstance(assistant_message, dict):
            raise OllamaResponseError("Ollama response is missing its message.")

        content = assistant_message.get("content", "")
        if not isinstance(content, str):
            raise OllamaResponseError("Ollama returned invalid assistant content.")
        tool_calls = assistant_message.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            raise OllamaResponseError("Ollama returned invalid tool calls.")
        if not content.strip() and not tool_calls:
            raise OllamaResponseError("Ollama returned an empty assistant response.")

        thinking = assistant_message.get("thinking", "")
        if not isinstance(thinking, str):
            thinking = ""
        return OllamaChatResponse(
            content=content.strip(),
            thinking=thinking.strip(),
            tool_calls=tool_calls,
        )
