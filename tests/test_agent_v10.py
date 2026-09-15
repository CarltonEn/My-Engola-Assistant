import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUB_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "_offline_stubs",
)

sys.path.insert(0, REPO_ROOT)

try:
    import fastapi  # noqa
    import openai  # noqa
    import webauthn  # noqa
except Exception:
    sys.path.insert(0, STUB_ROOT)


class TestLocalAgent(unittest.TestCase):

    def setUp(self):
        from core.db import db

        c = db()
        c.execute("DELETE FROM tasks")
        c.execute("DELETE FROM memories")
        c.commit()
        c.close()

    def test_create_task(self):
        from core.agent import run_local

        result = run_local("Create a task to review Engola")

        self.assertEqual(result.intent, "task.create")
        self.assertTrue(result.executed)
        self.assertTrue(result.verified)
        self.assertEqual(result.data["task"]["title"], "review Engola")

    def test_create_task_called_wording(self):
        from core.agent import run_local

        result = run_local("Create a task called HTTP Test Engola")

        self.assertEqual(result.intent, "task.create")
        self.assertTrue(result.executed)
        self.assertTrue(result.verified)
        self.assertEqual(result.data["task"]["title"], "HTTP Test Engola")

    def test_list_tasks(self):
        from core.agent import run_local

        run_local("Create a task to review Engola")
        result = run_local("Show my tasks")

        self.assertEqual(result.intent, "task.list")
        self.assertEqual(len(result.data["tasks"]), 1)

    def test_complete_task(self):
        from core.agent import run_local

        created = run_local("Create a task to review Engola")
        task_id = created.data["task"]["id"]

        result = run_local(f"Complete task #{task_id}")

        self.assertEqual(result.intent, "task.complete")
        self.assertTrue(result.executed)
        self.assertEqual(
            result.data["task"]["status"],
            "done",
        )

    def test_memory(self):
        from core.agent import run_local

        result = run_local("Remember that priority = Engola")

        self.assertEqual(result.intent, "memory.save")
        self.assertTrue(result.executed)

        result = run_local("Show my memory")

        self.assertEqual(result.intent, "memory.list")
        self.assertIn("priority", result.data["memory"])

    def test_briefing(self):
        from core.agent import run_local

        run_local("Create a task to finish the briefing")

        result = run_local("Give me my briefing")

        self.assertEqual(result.intent, "briefing")
        self.assertTrue(result.executed)
        self.assertIn("briefing", result.answer.lower())

    def test_unknown_request_is_honest(self):
        from core.agent import run_local

        result = run_local(
            "Book me a flight to London tomorrow"
        )

        self.assertEqual(result.intent, "unhandled")
        self.assertFalse(result.executed)
        self.assertIn("won't invent", result.answer.lower())


    def test_memory_called_wording(self):
        from core.agent import run_local

        result = run_local("Remember that my main project is called Engola")
        self.assertEqual(result.intent, "memory.save")
        self.assertEqual(result.data["key"], "my main project")
        self.assertEqual(result.data["value"], "Engola")

if __name__ == "__main__":
    unittest.main()
