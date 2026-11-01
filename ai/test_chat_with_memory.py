"""Offline unit tests for chat_with_memory.py. These do not require Ollama."""

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import chat_with_memory as chat


class MemoryTests(unittest.TestCase):
    def test_normalise_identifier(self):
        self.assertEqual(chat.normalise_identifier("Profile Name!"), "profile_name")

    def test_validate_proposed_fact_rejects_low_confidence(self):
        self.assertIsNone(chat.validate_proposed_fact({
            "category": "profile",
            "key": "name",
            "value": "Alex",
            "confidence": 0.2,
        }))

    def test_conflicting_automatic_update_is_not_applied(self):
        memory = {"version": 1, "facts": [{
            "category": "profile", "key": "name", "value": "Alex",
            "source": "test", "confidence": 1.0,
            "created_at": "old", "updated_at": "old",
        }]}
        fact = {"category": "profile", "key": "name", "value": "Sam", "confidence": 0.9}
        result = chat.upsert_fact(memory, fact, source="auto-extracted")
        self.assertEqual(result, "conflict")
        self.assertEqual(memory["facts"][0]["value"], "Alex")

    def test_manual_replace_is_possible(self):
        memory = {"version": 1, "facts": [{
            "category": "profile", "key": "name", "value": "Alex",
            "source": "test", "confidence": 1.0,
            "created_at": "old", "updated_at": "old",
        }]}
        fact = {"category": "profile", "key": "name", "value": "Sam", "confidence": 1.0}
        result = chat.upsert_fact(memory, fact, source="manual", allow_replace=True)
        self.assertEqual(result, "updated")
        self.assertEqual(memory["facts"][0]["value"], "Sam")

    def test_legacy_memory_migration_skips_placeholder(self):
        with tempfile.TemporaryDirectory() as temp:
            legacy = Path(temp) / "memory.md"
            legacy.write_text(
                "# Long-term memory\n\n"
                "Add personal facts here using the /remember command.\n"
                "- Prefers local AI\n",
                encoding="utf-8",
            )
            with patch.object(chat, "LEGACY_MEMORY_FILE", legacy):
                data = chat.migrate_legacy_memory()
        self.assertEqual(len(data["facts"]), 1)
        self.assertEqual(data["facts"][0]["value"], "Prefers local AI")


class HistoryTests(unittest.TestCase):
    def test_compaction_summarises_archives_and_keeps_recent_messages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            history_file = root / "chat_history.json"
            summary_file = root / "session_summary.md"
            archive_file = root / "chat_archive.jsonl"
            messages = []
            for number in range(13):
                messages.extend([
                    {"role": "user", "content": f"Question {number}"},
                    {"role": "assistant", "content": f"Answer {number}"},
                ])
            with (
                patch.object(chat, "HISTORY_FILE", history_file),
                patch.object(chat, "SUMMARY_FILE", summary_file),
                patch.object(chat, "ARCHIVE_FILE", archive_file),
                patch.object(chat, "MAX_ACTIVE_HISTORY_MESSAGES", 24),
                patch.object(chat, "KEEP_RECENT_MESSAGES", 12),
                patch.object(chat, "summarise_messages", return_value="A summary of older turns."),
            ):
                remaining = chat.compact_history(messages)
                self.assertEqual(len(remaining), 12)
                self.assertEqual(len(json.loads(history_file.read_text(encoding="utf-8"))), 12)
                self.assertEqual(summary_file.read_text(encoding="utf-8").strip(), "A summary of older turns.")
                archived = json.loads(archive_file.read_text(encoding="utf-8").splitlines()[0])
                self.assertEqual(archived["type"], "compaction")
                self.assertEqual(len(archived["messages"]), 14)

    def test_keyword_search_finds_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "chat_archive.jsonl"
            archive.write_text(json.dumps({
                "archived_at": "2026-01-01T12:00:00+00:00",
                "type": "session",
                "summary": "Discussed a Django food module.",
                "messages": [{"role": "user", "content": "We decided to build a food tracker."}],
            }) + "\n", encoding="utf-8")
            with patch.object(chat, "ARCHIVE_FILE", archive), patch.object(chat, "SUMMARY_FILE", root / "session_summary.md"):
                output = StringIO()
                with redirect_stdout(output):
                    chat.search_history("food tracker", [])
        self.assertIn("Found", output.getvalue())
        self.assertIn("food tracker", output.getvalue())


if __name__ == "__main__":
    unittest.main()
