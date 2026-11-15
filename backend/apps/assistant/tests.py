
import json
import socket

from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from django.test import SimpleTestCase, override_settings

from apps.assistant.services.ollama import (
    OllamaConnectionError,
    OllamaHTTPError,
    OllamaResponseError,
    OllamaService,
    OllamaTimeoutError,
)


@override_settings(
    OLLAMA_BASE_URL="http://localhost:11434",
    OLLAMA_MODEL="qwen3.5:4b",
    OLLAMA_TIMEOUT_SECONDS=120,
)
class OllamaServiceTests(SimpleTestCase):

    def setUp(self):
        self.service = OllamaService()

    @patch("apps.assistant.services.ollama.urlopen")
    def test_chat_returns_assistant_content(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "message": {
                "role": "assistant",
                "content": "Hello from Ollama!",
                "thinking": "This must not be returned.",
            }
        }).encode("utf-8")

        mock_urlopen.return_value = response

        result = self.service.chat("Hello")

        self.assertEqual(result.content, "Hello from Ollama!")
        self.assertEqual(result.thinking, "This must not be returned.")

        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(request.full_url, "http://localhost:11434/api/chat")
        self.assertEqual(payload["model"], "qwen3.5:4b")
        self.assertEqual(payload["messages"][0]["content"], "Hello")
        self.assertFalse(payload["stream"])
        self.assertTrue(payload["think"])

        mock_urlopen.assert_called_once_with(
            request,
            timeout=120,
        )

    @patch("apps.assistant.services.ollama.urlopen")
    def test_chat_includes_previous_conversation_history(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "message": {
                "role": "assistant",
                "content": "You said blue.",
            }
        }).encode("utf-8")
        mock_urlopen.return_value = response

        self.service.chat(
            "What colour did I say?",
            history=[
                {"role": "user", "content": "My favourite colour is blue."},
                {"role": "assistant", "content": "Got it."},
            ],
        )

        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            payload["messages"],
            [
                {"role": "user", "content": "My favourite colour is blue."},
                {"role": "assistant", "content": "Got it."},
                {"role": "user", "content": "What colour did I say?"},
            ],
        )

    @patch("apps.assistant.services.ollama.urlopen")
    def test_empty_message_is_rejected(self, mock_urlopen):
        with self.assertRaises(ValueError):
            self.service.chat("   ")

        mock_urlopen.assert_not_called()

    @patch("apps.assistant.services.ollama.urlopen")
    def test_connection_error(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("Connection refused")

        with self.assertRaises(OllamaConnectionError):
            self.service.chat("Hello")

    @patch("apps.assistant.services.ollama.urlopen")
    def test_timeout_error(self, mock_urlopen):
        mock_urlopen.side_effect = socket.timeout("Timed out")

        with self.assertRaises(OllamaTimeoutError):
            self.service.chat("Hello")

    @patch("apps.assistant.services.ollama.urlopen")
    def test_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="http://localhost:11434/api/chat",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )

        with self.assertRaises(OllamaHTTPError):
            self.service.chat("Hello")

    @patch("apps.assistant.services.ollama.urlopen")
    def test_invalid_json_response(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"not valid json"

        mock_urlopen.return_value = response

        with self.assertRaises(OllamaResponseError):
            self.service.chat("Hello")

    @patch("apps.assistant.services.ollama.urlopen")
    def test_missing_assistant_content(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "message": {
                "role": "assistant",
                "thinking": "Some internal output",
            }
        }).encode("utf-8")

        mock_urlopen.return_value = response

        with self.assertRaises(OllamaResponseError):
            self.service.chat("Hello")

    @patch("apps.assistant.services.ollama.urlopen")
    def test_missing_thinking_returns_empty_string(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "message": {
                "role": "assistant",
                "content": "Hello!",
            }
        }).encode("utf-8")

        mock_urlopen.return_value = response

        result = self.service.chat("Hello")

        self.assertEqual(result.content, "Hello!")
        self.assertEqual(result.thinking, "")

    @patch("apps.assistant.services.ollama.urlopen")
    def test_chat_messages_sends_tool_definitions_and_parses_tool_calls(self, mock_urlopen):
        response = MagicMock()
        tool_calls = [{"function": {"name": "get_daily_food_summary", "arguments": {}}}]
        response.__enter__.return_value.read.return_value = json.dumps({
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": tool_calls,
            }
        }).encode("utf-8")
        mock_urlopen.return_value = response

        tools = [{"type": "function", "function": {"name": "get_daily_food_summary"}}]
        result = self.service.chat_messages(
            [{"role": "system", "content": "Use tools when appropriate."},
             {"role": "user", "content": "How much protein today?"}],
            tools=tools,
        )

        self.assertEqual(result.content, "")
        self.assertEqual(result.tool_calls, tool_calls)
        payload = json.loads(mock_urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload["tools"], tools)
        self.assertEqual(payload["messages"][0]["role"], "system")
