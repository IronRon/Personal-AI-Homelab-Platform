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

        from apps.assistant.services.agent import DEFAULT_PERMISSIONS
        result = run_assistant_turn("How many calories today?", permissions=DEFAULT_PERMISSIONS)

        self.assertEqual(result["content"], "You have eaten 500 calories so far.")
        self.assertEqual(result["tools_used"], ["get_daily_food_summary"])
        self.assertIn("get_daily_food_summary", str(mock_chat.call_args_list[0]))
        self.assertEqual(mock_tool.call_args.args[0], "get_daily_food_summary")
        self.assertEqual(mock_tool.call_args.args[1], {})
        self.assertEqual(mock_chat.call_count, 2)


    @patch("apps.assistant.services.agent.OllamaService.chat_messages")
    def test_disabled_read_tools_are_not_sent_to_ollama(self, mock_chat):
        mock_chat.return_value = OllamaChatResponse(content="I cannot access Food records right now.")
        result = run_assistant_turn("How many calories today?", permissions={"read_enabled": False, "write_enabled": False, "read_tools": [], "write_tools": []})
        self.assertEqual(result["content"], "I cannot access Food records right now.")
        self.assertIsNone(result["pending_action"])
        self.assertIsNone(mock_chat.call_args.kwargs["tools"])

    @patch("apps.assistant.services.agent.validate_food_write_tool")
    @patch("apps.assistant.services.agent.OllamaService.chat_messages")
    def test_write_tool_creates_proposal_without_executing_it(self, mock_chat, mock_validate):
        mock_chat.return_value = OllamaChatResponse(content="", tool_calls=[{"function": {"name": "create_food_item", "arguments": {"name": "Chicken", "item_type": "ingredient", "nutrition_basis_unit": "g"}}}])
        mock_validate.return_value = {"name": "Chicken"}
        permissions = {"read_enabled": False, "write_enabled": True, "read_tools": [], "write_tools": ["create_food_item"]}
        result = run_assistant_turn("Add chicken to my catalogue.", permissions=permissions)
        self.assertEqual(result["pending_action"]["name"], "create_food_item")
        self.assertEqual(result["pending_action"]["preview"], {"name": "Chicken"})
        self.assertIn("confirm", result["content"].lower())
