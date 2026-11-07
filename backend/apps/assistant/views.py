import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .services.agent import DEFAULT_PERMISSIONS, READ_TOOL_NAMES, run_assistant_turn
from .services.food_write_tools import FOOD_WRITE_TOOL_NAMES, execute_food_write_tool
from .services.ollama import (
    OllamaConnectionError,
    OllamaHTTPError,
    OllamaResponseError,
    OllamaTimeoutError,
)

SESSION_MESSAGES_KEY = "assistant_chat_messages"
MAX_MESSAGE_LENGTH = 8000
MAX_HISTORY_MESSAGES = 40
SETTINGS_SESSION_KEY = "assistant_permissions"
PENDING_ACTION_SESSION_KEY = "assistant_pending_food_action"


def _permissions(request):
    saved = request.session.get(SETTINGS_SESSION_KEY, {})
    permissions = {
        "read_enabled": bool(saved.get("read_enabled", DEFAULT_PERMISSIONS["read_enabled"])),
        "write_enabled": bool(saved.get("write_enabled", DEFAULT_PERMISSIONS["write_enabled"])),
        "read_tools": sorted(set(saved.get("read_tools", DEFAULT_PERMISSIONS["read_tools"])) & READ_TOOL_NAMES),
        "write_tools": sorted(set(saved.get("write_tools", DEFAULT_PERMISSIONS["write_tools"])) & FOOD_WRITE_TOOL_NAMES),
    }
    return permissions


def chat_page(request):
    """Render the chat interface and current session conversation."""
    return render(
        request,
        "assistant/chat.html",
        {
            "chat_messages": request.session.get(SESSION_MESSAGES_KEY, []),
            "ollama_model": settings.OLLAMA_MODEL,
            "assistant_permissions": _permissions(request),
            "read_tool_names": sorted(READ_TOOL_NAMES),
            "write_tool_names": sorted(FOOD_WRITE_TOOL_NAMES),
            "pending_action": request.session.get(PENDING_ACTION_SESSION_KEY),
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

    if request.session.get(PENDING_ACTION_SESSION_KEY):
        return JsonResponse({"error": "Please confirm or cancel the pending Food change before sending another message."}, status=409)

    stored_messages = request.session.get(SESSION_MESSAGES_KEY, [])
    history = [
        {"role": item["role"], "content": item["content"]}
        for item in stored_messages
        if item.get("role") in ("user", "assistant")
        and isinstance(item.get("content"), str)
    ][-MAX_HISTORY_MESSAGES:]

    try:
        result = run_assistant_turn(message, history=history, permissions=_permissions(request))
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
            "content": result["content"],
            "thinking": result["thinking"],
            "tools_used": result["tools_used"],
        },
    ])
    request.session[SESSION_MESSAGES_KEY] = stored_messages[-MAX_HISTORY_MESSAGES:]
    if result.get("pending_action"):
        request.session[PENDING_ACTION_SESSION_KEY] = result["pending_action"]
    request.session.modified = True

    return JsonResponse({
        "answer": result["content"],
        "thinking": result["thinking"],
        "tools_used": result["tools_used"],
        "pending_action": result.get("pending_action"),
        "model": settings.OLLAMA_MODEL,
    })


@require_POST
def new_conversation(request):
    """Clear the assistant conversation in the current browser session."""
    request.session.pop(SESSION_MESSAGES_KEY, None)
    request.session.pop(PENDING_ACTION_SESSION_KEY, None)
    return JsonResponse({"ok": True})


@require_POST
def assistant_settings_api(request):
    """Read or update per-browser-session tool permissions."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "The request was not valid JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "The request must be a JSON object."}, status=400)
    current = _permissions(request)
    for key in ("read_enabled", "write_enabled"):
        if key in payload:
            if not isinstance(payload[key], bool):
                return JsonResponse({"error": f"{key} must be true or false."}, status=400)
            current[key] = payload[key]
    for key, allowed in (("read_tools", READ_TOOL_NAMES), ("write_tools", FOOD_WRITE_TOOL_NAMES)):
        if key in payload:
            value = payload[key]
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                return JsonResponse({"error": f"{key} must be a list of function names."}, status=400)
            if not set(value) <= allowed:
                return JsonResponse({"error": f"{key} contains an unknown function."}, status=400)
            current[key] = sorted(set(value))
    request.session[SETTINGS_SESSION_KEY] = current
    request.session.modified = True
    return JsonResponse({"settings": current})


@require_POST
def confirm_food_action(request):
    """Execute the exact server-stored proposal after an explicit confirmation click."""
    pending = request.session.get(PENDING_ACTION_SESSION_KEY)
    if not isinstance(pending, dict):
        return JsonResponse({"error": "There is no pending Food change to confirm."}, status=400)
    permissions = _permissions(request)
    name = pending.get("name")
    if not permissions["write_enabled"] or name not in permissions["write_tools"]:
        return JsonResponse({"error": "Food write access or this function is no longer enabled. The proposed change was not made."}, status=403)
    try:
        result = execute_food_write_tool(name, pending.get("arguments", {}))
    except (ValueError, TypeError, ValidationError) as exc:
        return JsonResponse({"error": str(exc), "pending_action": pending}, status=400)
    request.session.pop(PENDING_ACTION_SESSION_KEY, None)
    messages = request.session.get(SESSION_MESSAGES_KEY, [])
    messages.append({"role": "assistant", "content": f"Confirmed and completed: {result.get('name') or result.get('food') or result.get('created')} (ID {result.get('id')}).", "thinking": "", "tools_used": [name]})
    request.session[SESSION_MESSAGES_KEY] = messages[-MAX_HISTORY_MESSAGES:]
    request.session.modified = True
    return JsonResponse({"ok": True, "result": result, "message": messages[-1]})


@require_POST
def cancel_food_action(request):
    request.session.pop(PENDING_ACTION_SESSION_KEY, None)
    return JsonResponse({"ok": True})
