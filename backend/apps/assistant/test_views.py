import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse



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
        mock_chat.assert_called_once_with("Hello", history=[])

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
