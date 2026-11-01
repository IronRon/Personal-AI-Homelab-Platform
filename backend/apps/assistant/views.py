import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .services.ollama import (
    OllamaConnectionError,
    OllamaHTTPError,
    OllamaResponseError,
    OllamaService,
    OllamaTimeoutError,
)

SESSION_MESSAGES_KEY = "assistant_chat_messages"
MAX_MESSAGE_LENGTH = 8000
MAX_HISTORY_MESSAGES = 40


def chat_page(request):
    """Render the chat interface and current session conversation."""
    return render(
        request,
        "assistant/chat.html",
        {
            "chat_messages": request.session.get(SESSION_MESSAGES_KEY, []),
            "ollama_model": settings.OLLAMA_MODEL,
        },
    )


@require_POST
def chat_api(request):
    """Send a message to Ollama and retain the conversation in the session."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "The request was not valid JSON."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "The request must be a JSON object."}, status=400)

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return JsonResponse({"error": "Please enter a message."}, status=400)

    message = message.strip()
    if len(message) > MAX_MESSAGE_LENGTH:
        return JsonResponse(
            {"error": f"Messages must be {MAX_MESSAGE_LENGTH} characters or fewer."},
            status=400,
        )

    stored_messages = request.session.get(SESSION_MESSAGES_KEY, [])
    history = [
        {"role": item["role"], "content": item["content"]}
        for item in stored_messages
        if item.get("role") in ("user", "assistant")
        and isinstance(item.get("content"), str)
    ][-MAX_HISTORY_MESSAGES:]

    try:
        result = OllamaService().chat(message, history=history)
    except OllamaConnectionError:
        return JsonResponse(
            {"error": "Could not connect to Ollama. Make sure Ollama is running on this PC."},
            status=503,
        )
    except OllamaTimeoutError:
        return JsonResponse(
            {"error": "Ollama took too long to respond. Try again in a moment."},
            status=504,
        )
    except (OllamaHTTPError, OllamaResponseError):
        return JsonResponse(
            {"error": "Ollama returned an unexpected response. Check that the model is available."},
            status=502,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    stored_messages.extend([
        {"role": "user", "content": message},
        {
            "role": "assistant",
            "content": result.content,
            "thinking": result.thinking,
        },
    ])
    request.session[SESSION_MESSAGES_KEY] = stored_messages[-MAX_HISTORY_MESSAGES:]
    request.session.modified = True

    return JsonResponse({
        "answer": result.content,
        "thinking": result.thinking,
        "model": settings.OLLAMA_MODEL,
    })


@require_POST
def new_conversation(request):
    """Clear the assistant conversation in the current browser session."""
    request.session.pop(SESSION_MESSAGES_KEY, None)
    return JsonResponse({"ok": True})
