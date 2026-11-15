import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.assistant.services.agent import DEFAULT_PERMISSIONS



class AssistantChatViewTests(TestCase):
    def test_chat_page_renders_model_and_prompt_interface(self):
        response = self.client.get(reverse("assistant_chat"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Assistant")
        self.assertContains(response, "qwen3.5:4b")
        self.assertContains(response, "Today's calories and protein")

    @patch("apps.assistant.views.run_assistant_turn")
    def test_chat_api_sends_message_and_saves_conversation(self, mock_chat):
        mock_chat.return_value = {
            "content": "Hello from the local model.",
            "thinking": "I am considering the response.",
            "tools_used": [],
        }

        response = self.client.post(
            reverse("assistant_chat_api"),
            data=json.dumps({"message": "Hello"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Hello from the local model.")
        self.assertEqual(response.json()["thinking"], "I am considering the response.")
        self.assertEqual(response.json()["tools_used"], [])
        mock_chat.assert_called_once_with("Hello", history=[], permissions=DEFAULT_PERMISSIONS)

        page = self.client.get(reverse("assistant_chat"))
        self.assertContains(page, "Hello from the local model.")

    @patch("apps.assistant.views.run_assistant_turn")
    def test_follow_up_includes_previous_turns_as_context(self, mock_chat):
        mock_chat.return_value = {"content": "I remember.", "thinking": "", "tools_used": []}

        self.client.post(
            reverse("assistant_chat_api"),
            data=json.dumps({"message": "My favourite colour is blue."}),
            content_type="application/json",
        )
        self.client.post(
            reverse("assistant_chat_api"),
            data=json.dumps({"message": "What is my favourite colour?"}),
            content_type="application/json",
        )

        history = mock_chat.call_args.kwargs["history"]
        self.assertEqual(history[0], {
            "role": "user",
            "content": "My favourite colour is blue.",
        })
        self.assertEqual(history[1], {
            "role": "assistant",
            "content": "I remember.",
        })

    def test_chat_api_rejects_blank_message(self):
        response = self.client.post(
            reverse("assistant_chat_api"),
            data=json.dumps({"message": "   "}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_new_conversation_clears_session_history(self):
        session = self.client.session
        session["assistant_chat_messages"] = [
            {"role": "user", "content": "Old message"}
        ]
        session.save()

        response = self.client.post(reverse("assistant_new_conversation"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("assistant_chat_messages", self.client.session)


    def test_settings_default_to_read_only(self):
        response = self.client.get(reverse("assistant_chat"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enable Food read access")
        self.assertContains(response, "Enable Food write access")
        self.assertNotIn("assistant_permissions", self.client.session)

    def test_settings_reject_unknown_tool_names(self):
        response = self.client.post(
            reverse("assistant_settings_api"),
            data=json.dumps({"write_tools": ["delete_everything"]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_settings_can_enable_write_and_select_a_function(self):
        response = self.client.post(
            reverse("assistant_settings_api"),
            data=json.dumps({"write_enabled": True, "write_tools": ["create_food_item"]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["settings"]["write_enabled"])
        self.assertEqual(response.json()["settings"]["write_tools"], ["create_food_item"])

    @patch("apps.assistant.views.execute_food_write_tool")
    def test_pending_write_requires_confirmation_and_executes_server_stored_action(self, mock_execute):
        session = self.client.session
        session["assistant_permissions"] = {"read_enabled": True, "write_enabled": True, "read_tools": [], "write_tools": ["create_food_item"]}
        session["assistant_pending_food_action"] = {"name": "create_food_item", "arguments": {"name": "Chicken", "item_type": "ingredient", "nutrition_basis_unit": "g"}, "preview": {"name": "Chicken"}}
        session.save()
        mock_execute.return_value = {"created": "food_item", "id": 12, "name": "Chicken"}

        response = self.client.post(reverse("assistant_confirm_food_action"))

        self.assertEqual(response.status_code, 200)
        mock_execute.assert_called_once_with("create_food_item", {"name": "Chicken", "item_type": "ingredient", "nutrition_basis_unit": "g"})
        self.assertNotIn("assistant_pending_food_action", self.client.session)

    @patch("apps.assistant.views.execute_food_write_tool")
    def test_pending_write_cannot_execute_after_write_access_is_disabled(self, mock_execute):
        session = self.client.session
        session["assistant_permissions"] = {"read_enabled": True, "write_enabled": False, "read_tools": [], "write_tools": ["create_food_item"]}
        session["assistant_pending_food_action"] = {"name": "create_food_item", "arguments": {}, "preview": {}}
        session.save()

        response = self.client.post(reverse("assistant_confirm_food_action"))

        self.assertEqual(response.status_code, 403)
        mock_execute.assert_not_called()
