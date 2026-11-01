
import json
import socket
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


@dataclass(frozen=True)
class OllamaChatResponse:
    """Final response and optional reasoning returned by Ollama."""

    content: str
    thinking: str = ""


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

    def chat(self, message: str, history=None) -> OllamaChatResponse:
        """Send a message with optional prior conversation context."""

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
                content = item.get("content")
                if role not in ("user", "assistant") or not isinstance(content, str):
                    raise ValueError("Conversation history contains an invalid message.")
                if content.strip():
                    conversation.append({"role": role, "content": content.strip()})

        conversation.append({"role": "user", "content": message.strip()})

        payload = {
            "model": self.model,
            "messages": conversation,
            "stream": False,
            "think": settings.OLLAMA_THINK,
        }

        request = Request(
            url=f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                response_body = response.read()

        except HTTPError as exc:
            raise OllamaHTTPError(
                f"Ollama returned HTTP {exc.code}."
            ) from exc

        except (socket.timeout, TimeoutError) as exc:
            raise OllamaTimeoutError(
                "Ollama took too long to respond."
            ) from exc

        except URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise OllamaTimeoutError(
                    "Ollama took too long to respond."
                ) from exc

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
            raise OllamaResponseError(
                "Ollama returned invalid JSON."
            ) from exc

        if not isinstance(data, dict):
            raise OllamaResponseError(
                "Ollama returned an unexpected response."
            )

        assistant_message = data.get("message")

        if not isinstance(assistant_message, dict):
            raise OllamaResponseError(
                "Ollama response is missing its message."
            )

        content = assistant_message.get("content")

        if not isinstance(content, str) or not content.strip():
            raise OllamaResponseError(
                "Ollama returned an empty assistant response."
            )

        thinking = assistant_message.get("thinking", "")

        # Thinking is optional because not every model supports it.
        if not isinstance(thinking, str):
            thinking = ""

        return OllamaChatResponse(
            content=content.strip(),
            thinking=thinking.strip(),
        )
