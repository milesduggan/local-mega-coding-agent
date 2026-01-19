import os
import json
from typing import List, Dict
from datetime import datetime


class ContextManager:
    """Manages tiered context with sliding window and persistent memory."""

    def __init__(self, storage_dir: str, max_recent_messages: int = 8):
        self.storage_dir = storage_dir
        self.max_recent_messages = max_recent_messages
        self.project_context_file = os.path.join(storage_dir, "project_context.json")
        self.session_file = os.path.join(storage_dir, "session_history.json")
        os.makedirs(storage_dir, exist_ok=True)

    def get_project_context(self) -> str:
        """Load persistent project context."""
        if os.path.exists(self.project_context_file):
            with open(self.project_context_file, 'r') as f:
                data = json.load(f)
                return data.get("summary", "")
        return ""

    def update_project_context(self, new_learning: str) -> None:
        """Add a new learning to project context."""
        data = {"summary": "", "learnings": [], "updated": ""}
        if os.path.exists(self.project_context_file):
            with open(self.project_context_file, 'r') as f:
                data = json.load(f)

        data["learnings"].append({
            "content": new_learning,
            "timestamp": datetime.now().isoformat()
        })
        # Keep only last 10 learnings
        data["learnings"] = data["learnings"][-10:]
        data["summary"] = "\n".join(l["content"] for l in data["learnings"])
        data["updated"] = datetime.now().isoformat()

        with open(self.project_context_file, 'w') as f:
            json.dump(data, f, indent=2)

    def get_session_summary(self) -> str:
        """Get summary of previous session."""
        if os.path.exists(self.session_file):
            with open(self.session_file, 'r') as f:
                data = json.load(f)
                return data.get("summary", "")
        return ""

    def save_session_summary(self, summary: str) -> None:
        """Save current session summary for next time."""
        with open(self.session_file, 'w') as f:
            json.dump({
                "summary": summary,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)

    def build_context(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        current_message: str
    ) -> List[Dict[str, str]]:
        """Build tiered context for LLM call."""
        messages = []

        # Tier 1: System prompt
        full_system = system_prompt

        # Tier 2: Project context
        project_ctx = self.get_project_context()
        if project_ctx:
            full_system += f"\n\n## Project Context\n{project_ctx}"

        # Tier 3: Session summary (if we have old messages)
        session_summary = self.get_session_summary()
        if session_summary:
            full_system += f"\n\n## Previous Session\n{session_summary}"

        messages.append({"role": "system", "content": full_system})

        # Tier 4: Recent messages (sliding window)
        if len(history) > self.max_recent_messages:
            # Summarize older messages (simple approach: just take key points)
            old_messages = history[:-self.max_recent_messages]
            summary_text = self._summarize_messages(old_messages)
            if summary_text:
                messages.append({
                    "role": "system",
                    "content": f"[Earlier in conversation: {summary_text}]"
                })
            recent = history[-self.max_recent_messages:]
        else:
            recent = history

        # Add recent history
        for msg in recent:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Tier 5: Current message
        messages.append({"role": "user", "content": current_message})

        return messages

    def _summarize_messages(self, messages: List[Dict[str, str]]) -> str:
        """Simple extractive summary of messages."""
        # For now, just extract key topics mentioned
        # Could be enhanced with LLM-based summarization later
        topics = []
        for msg in messages:
            content = msg["content"][:100]  # First 100 chars
            if msg["role"] == "user":
                topics.append(f"User asked about: {content}...")
        return " | ".join(topics[-3:])  # Last 3 topics
