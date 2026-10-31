"""Validate status handling with a mocked browser-use backend (no agent runs)."""
import importlib
import json
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class AgentResultTests(unittest.IsolatedAsyncioTestCase):
    async def run_result(self, **fields):
        backend = types.ModuleType("browser_use")
        for name in ("ActionResult", "Agent", "Browser", "ChatGoogle", "Tools"):
            setattr(backend, name, MagicMock())
        with patch.dict(sys.modules, {"browser_use": backend}):
            agent = importlib.import_module("outreach.agent")
        history = MagicMock()
        result = {"filled": True, "filled_fields": ["email", "message"], "has_captcha": False, "no_sales_notice": False, "note": "", **fields}
        history.final_result.return_value = json.dumps(result)
        browser = MagicMock(); browser.kill = AsyncMock()
        runner = MagicMock(); runner.run = AsyncMock(return_value=history)
        with patch.object(agent, "Browser", return_value=browser), patch.object(agent, "Agent", return_value=runner), patch.object(agent, "make_llm", return_value=MagicMock()):
            return await agent.fill_form("https://unit.test/contact", {"sender": {"name": "Test"}, "auto_submit": True}, {"subject": "Test", "body": "Draft"}, wait_human=False, headless=True)

    async def test_filled_does_not_imply_submitted(self):
        self.assertEqual((await self.run_result())[0], "filled")

    async def test_submission_needs_completion_evidence(self):
        self.assertEqual((await self.run_result(submitted=True))[0], "filled")

    async def test_explicit_completion_can_be_sent(self):
        self.assertEqual((await self.run_result(submitted=True, submission_evidence="送信が完了しました"))[0], "sent")

    async def test_captcha_prevents_success_status(self):
        self.assertEqual((await self.run_result(submitted=True, submission_evidence="送信が完了しました", has_captcha=True))[0], "filled")


if __name__ == "__main__":
    unittest.main()
