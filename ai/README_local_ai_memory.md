# Local Ollama Memory Experiment

This is a small, dependency-free Python experiment using a locally running Ollama server. It expands `chat_with_memory.py` with three stages:

1. **Structured long-term memory** in `memory.json`. Qwen proposes facts as JSON; Python validates the shape and saves additions. Conflicting automatic updates are skipped instead of silently overwriting existing facts.
2. **Rolling session summaries** in `session_summary.md`. Once the active history becomes too long, older messages are summarised and archived, leaving only recent messages in the prompt.
3. **Keyword search** across the active chat, current summary, and archived messages using `/search`.

It uses only the Python standard library. You need Python 3.10+ and Ollama running locally with the model configured at the top of the script.

## Run it

1. Put `chat_with_memory.py` in a folder, such as `Documents\LocalAI`.
2. Make sure Ollama is running and Qwen is installed. In PowerShell:

   ```powershell
   ollama list
   ollama pull qwen3.5:4b
   ```

3. In PowerShell, change directory to the folder containing the script, then run:

   ```powershell
   py chat_with_memory.py
   ```

If your model has a different Ollama tag, edit `MODEL` near the top of `chat_with_memory.py`.

## Commands

- `/help` — show commands.
- `/memory` — list saved facts.
- `/remember profile.name = Alex` — manually create or deliberately update a fact.
- `/forget profile.name` — delete a fact.
- `/learn` — ask Qwen to extract stable facts from the current chat and session summary.
- `/summary` — view the current session summary.
- `/search food module` — keyword-search active and archived history.
- `/new` — learn facts, archive the current session, and start a fresh conversation.
- `/bye` — attempt to learn facts and exit. The active conversation stays available when the script is next opened.

Automatic memory extraction runs on `/learn`, `/new`, and `/bye` (or Ctrl+C/EOF), rather than on every normal message. That avoids an extra model call for every answer. You can trigger it at any time with `/learn`.

## Files created beside the script

- `memory.json` — categorised facts such as `profile.name` and `projects.main_project`.
- `chat_history.json` — current active conversation messages.
- `session_summary.md` — the rolling summary of older messages in the current conversation.
- `chat_archive.jsonl` — archived message chunks and finished conversations, one JSON record per line.
- `memory.md` — if present from the earlier version, its bullet entries are imported into `memory.json` the first time the new script runs. The old file is not deleted.

The archive can continue to grow on disk. It is not all sent to the model; it is searched locally when you use `/search`. A retention/cleanup policy could be added later if you want to limit disk usage.

## Safety and limitations

- Memory extraction is a best-effort local model operation; inspect `/memory` and correct it when necessary.
- The model proposes new facts but does not directly write files. The Python program validates and saves them.
- Automatic extraction will not silently replace a conflicting saved fact. Use `/remember category.key = value` to deliberately change a fact.
- Search is simple keyword search, not semantic/vector search.
- Summary generation is lossy. The raw older messages are archived before they are removed from active context, so you can search them later.
- Don't store passwords, API keys, account numbers, or other secrets in the memory or chat files.
- Everything is stored as plain text/JSON beside the script. Keep the folder private if the conversations contain personal information.
