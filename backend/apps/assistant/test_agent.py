from unittest.mock import patch

from django.test import SimpleTestCase

from apps.assistant.services.agent import run_assistant_turn
from apps.assistant.services.ollama import OllamaChatResponse


class AssistantAgentTests(SimpleTestCase):
    @patch("apps.assistant.services.agent.execute_food_tool")
    @patch("apps.assistant.services.agent.OllamaService.chat_messages")
    def test_executes_read_tool_then_returns_final_answer(self, mock_chat, mock_tool):
        mock_chat.side_effect = [
            OllamaChatResponse(
                content="",
                thinking="I should check today's food log.",
                tool_calls=[{
                    "function": {
                        "name": "get_daily_food_summary",
                        "arguments": {},
                    }
                }],
            ),
            OllamaChatResponse(
                content="You have eaten 500 calories so far.",
                thinking="The tool returned 500 calories.",
            ),
        ]
        mock_tool.return_value = {"calories": "500.00"}

        result = run_assistant_turn("How many calories today?")

        self.assertEqual(result["content"], "You have eaten 500 calories so far.")
        self.assertEqual(result["tools_used"], ["get_daily_food_summary"])
        self.assertIn("get_daily_food_summary", str(mock_chat.call_args_list[0]))
        self.assertEqual(mock_tool.call_args.args[0], "get_daily_food_summary")
        self.assertEqual(mock_tool.call_args.args[1], {})
        self.assertEqual(mock_chat.call_count, 2)
