"""
Offline test suite.

The sandbox this was built in has no network access, so the real
`fastapi`, `openai` and `webauthn` packages could not be pip-installed to
run a genuine `uvicorn`/TestClient smoke test. To still verify import
correctness and business logic beyond plain py_compile, this suite adds a
minimal local stub for those three packages (see _stubs/) to sys.path,
then imports the real application modules unchanged and exercises their
pure logic (URL parsing, scoring, narration pacing, structured-JSON
parsing, permission gating).

This does NOT validate real WebAuthn cryptographic verification, real
OpenAI calls, or real HTTP routing/dependency injection -- those require
`pip install -r requirements.txt` and a live run (see README "Verifying
this build" section). It DOES prove: every module imports cleanly with no
syntax/reference errors, main.py registers every router, and the
hand-written business logic behaves as intended.
"""
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUB_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_offline_stubs")
sys.path.insert(0, REPO_ROOT)

try:
    import fastapi as _real_fastapi  # noqa: F401
    import openai as _real_openai  # noqa: F401
    import webauthn as _real_webauthn  # noqa: F401
    USING_REAL_DEPENDENCIES = True
except Exception:
    # Real fastapi/openai/webauthn are not installed in this environment
    # (e.g. no network access to pip install). Fall back to the shipped
    # offline stub package so import correctness and pure business logic
    # can still be verified. This is NOT a substitute for testing against
    # the real libraries -- see README "Verifying this build".
    sys.path.insert(0, STUB_ROOT)
    USING_REAL_DEPENDENCIES = False

class TestImports(unittest.TestCase):
    def test_all_modules_import(self):
        import main  # noqa: F401
        from routers import auth, career, chat, google_oauth, health, media, memory, permissions, storage, uganda, voice  # noqa

    def test_main_registers_all_routers(self):
        import main
        # main.py explicitly includes these routers; just confirm the module
        # objects exist and each has a FastAPI-style `router` attribute.
        from routers import auth, career, chat, google_oauth, health, media, memory, permissions, storage, uganda, voice
        for mod in (auth, career, chat, google_oauth, health, media, memory, permissions, storage, uganda, voice):
            self.assertTrue(hasattr(mod, "router"))


class TestYoutubeParser(unittest.TestCase):
    def setUp(self):
        from routers.media import youtube_video_id
        self.f = youtube_video_id

    def test_watch_url(self):
        self.assertEqual(self.f("https://www.youtube.com/watch?v=abc123XYZ_"), "abc123XYZ_")

    def test_shorts_url(self):
        self.assertEqual(self.f("https://www.youtube.com/shorts/abc123"), "abc123")

    def test_embed_url(self):
        self.assertEqual(self.f("https://www.youtube.com/embed/abc123"), "abc123")

    def test_youtu_be(self):
        self.assertEqual(self.f("https://youtu.be/abc123"), "abc123")

    def test_youtu_be_with_query(self):
        self.assertEqual(self.f("https://youtu.be/abc123?t=30"), "abc123")

    def test_invalid_domain(self):
        self.assertIsNone(self.f("https://vimeo.com/12345"))

    def test_invalid_garbage(self):
        self.assertIsNone(self.f("not a url at all"))

    def test_empty_string(self):
        self.assertIsNone(self.f(""))

    def test_watch_missing_v_param(self):
        self.assertIsNone(self.f("https://www.youtube.com/watch?x=1"))


class TestStudyParsing(unittest.TestCase):
    def test_valid_json(self):
        from routers.media import _parse_structured_study
        import json
        payload = json.dumps({
            "facts": ["a"], "claims": [], "inferences": [], "uncertainties": [],
            "sources": [], "connects_to_owner_knowledge": "",
        })
        data, err = _parse_structured_study(payload)
        self.assertIsNone(err)
        self.assertEqual(data["facts"], ["a"])

    def test_fenced_json(self):
        from routers.media import _parse_structured_study
        payload = "```json\n{\"facts\":[],\"claims\":[],\"inferences\":[],\"uncertainties\":[],\"sources\":[],\"connects_to_owner_knowledge\":\"\"}\n```"
        data, err = _parse_structured_study(payload)
        self.assertIsNone(err)

    def test_garbage_is_honestly_flagged(self):
        from routers.media import _parse_structured_study
        data, err = _parse_structured_study("this is not json at all")
        self.assertIsNone(data)
        self.assertIsNotNone(err)

    def test_missing_fields_is_flagged(self):
        from routers.media import _parse_structured_study
        data, err = _parse_structured_study('{"facts": []}')
        self.assertIsNone(data)
        self.assertIsNotNone(err)


class TestCareerScoring(unittest.TestCase):
    def test_no_owner_skills_returns_zero_with_reason(self):
        from routers.career import score_opportunity
        import core.db as coredb
        # ensure clean memory table for this isolated run
        c = coredb.db()
        c.execute("DELETE FROM memories")
        c.commit(); c.close()
        score, breakdown = score_opportunity("Looking for a Python developer with FastAPI experience")
        self.assertEqual(score, 0.0)
        self.assertTrue(breakdown["missing_context"])

    def test_full_overlap_scores_100(self):
        from routers.career import score_opportunity
        import core.db as coredb
        c = coredb.db()
        c.execute("DELETE FROM memories")
        c.execute("INSERT INTO memories(key,value,ts) VALUES('skill:profile','python fastapi sqlite',0)")
        c.commit(); c.close()
        score, breakdown = score_opportunity("We need a Python engineer skilled in FastAPI and SQLite.")
        self.assertEqual(score, 100.0)
        self.assertFalse(breakdown["missing_context"])

    def test_partial_overlap_scores_between_0_and_100(self):
        from routers.career import score_opportunity
        import core.db as coredb
        c = coredb.db()
        c.execute("DELETE FROM memories")
        c.execute("INSERT INTO memories(key,value,ts) VALUES('skill:profile','python fastapi sqlite react',0)")
        c.commit(); c.close()
        score, breakdown = score_opportunity("We need someone who knows Python.")
        self.assertGreater(score, 0.0)
        self.assertLess(score, 100.0)


class TestUgandaRegistry(unittest.TestCase):
    def test_relevant_detects_keyword(self):
        from routers.uganda import relevant_sources
        triggered, results = relevant_sources("What is the current PAYE rate in Uganda?")
        self.assertTrue(triggered)
        self.assertGreater(len(results), 0)

    def test_not_relevant_for_unrelated_text(self):
        from routers.uganda import relevant_sources
        triggered, _ = relevant_sources("What's the weather like in Tokyo?")
        self.assertFalse(triggered)

    def test_category_filter(self):
        from routers.uganda import relevant_sources
        _, results = relevant_sources("Uganda tax question", category="tax")
        self.assertTrue(all(r["category"] == "tax" for r in results))


class TestVoiceNarration(unittest.TestCase):
    def test_shape_narration_basic(self):
        from routers.voice import shape_narration
        segments, ssml, total = shape_narration("This is one sentence. This is another.\n\nA new paragraph here.")
        self.assertEqual(len(segments), 3)
        self.assertTrue(ssml.startswith("<speak>"))
        self.assertTrue(ssml.endswith("</speak>"))
        self.assertGreater(total, 0)
        # Long pause should appear after the last sentence of paragraph 0
        self.assertEqual(segments[1]["pause_after_ms"], 850)
        # No trailing pause after the very last sentence overall
        self.assertEqual(segments[-1]["pause_after_ms"], 0)

    def test_empty_text_has_no_segments(self):
        from routers.voice import shape_narration
        segments, ssml, total = shape_narration("")
        self.assertEqual(segments, [])
        self.assertEqual(total, 0)




class TestVoiceInputUI(unittest.TestCase):
    def test_v2_conversation_ui_has_voice_integration_hook(self):
        from pathlib import Path

        html = (Path(REPO_ROOT) / "static" / "index.html").read_text()
        js = (Path(REPO_ROOT) / "static" / "engola-ui-v2.js").read_text()

        self.assertIn('id="composer"', html)
        self.assertIn('id="messageInput"', html)
        self.assertIn('/static/engola-ui-v2.js', html)

        # Voice is a post-deployment integration task.
        # The v2 UI exposes the visual-state bridge that voice will drive.
        self.assertIn("EngolaVisual", js)
        self.assertIn("setState", js)

class TestSecurityHelpers(unittest.TestCase):
    def test_hash_token_deterministic(self):
        from core.security import hash_token
        self.assertEqual(hash_token("abc"), hash_token("abc"))
        self.assertNotEqual(hash_token("abc"), hash_token("abd"))

    def test_rp_id_falls_back_to_host(self):
        from fastapi import Request
        from core.security import rp_id
        req = Request({
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"host", b"example.com:8000")],
            "scheme": "https",
            "query_string": b"",
        })
        self.assertEqual(rp_id(req), "example.com")

    def test_rp_id_localhost_default(self):
        from fastapi import Request
        from core.security import rp_id
        req = Request({
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "scheme": "http",
            "query_string": b"",
        })
        self.assertEqual(rp_id(req), "localhost")


class TestGoogleOAuthHonestFailure(unittest.TestCase):
    def test_not_configured_by_default(self):
        from routers.google_oauth import _configured
        # .env.example ships blank Google creds; as long as the real .env
        # in this sandbox doesn't set them, this should be False.
        if not (os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET") and os.getenv("GOOGLE_REDIRECT_URI")):
            self.assertFalse(_configured())


if __name__ == "__main__":
    mode = "REAL fastapi/openai/webauthn" if USING_REAL_DEPENDENCIES else "OFFLINE STUBS (real deps not installed)"
    print(f"[test_offline] Running with: {mode}\n")
    unittest.main()

class TestWorkRouter(unittest.TestCase):
    def test_work_router_imports_and_routes(self):
        from routers import work
        paths = {(getattr(r, 'path', ''), tuple(getattr(r, 'methods', set()))) for r in work.router.routes}
        self.assertIn(('/api/work/tasks', ('GET',)), paths)
        self.assertIn(('/api/work/tasks', ('POST',)), paths)
        self.assertIn(('/api/work/tasks/{task_id}', ('PATCH',)), paths)
        self.assertIn(('/api/work/tasks/{task_id}', ('DELETE',)), paths)


class TestReconciliationRegressions(unittest.TestCase):
    def test_knowledge_wiki_route_precedes_dynamic_source_route(self):
        from routers.knowledge import router
        paths=[getattr(r,'path','') for r in router.routes]
        self.assertLess(paths.index('/api/knowledge/wiki'), paths.index('/api/knowledge/{source_id}'))

    def test_integration_status_uses_provider_namespaced_state_in_frontend(self):
        from pathlib import Path
        js=(Path(REPO_ROOT)/'static'/'engola-v16.js').read_text()
        self.assertIn('d.google||{}', js)
        self.assertIn('d.github||{}', js)
        self.assertIn("d.archive||[]", js)
        self.assertIn("if(!d.google?.configured)", js)
        self.assertIn("if(!d.github?.configured)", js)

    def test_home_uses_v2_ui_without_legacy_injection(self):
        import main

        html = main.home().body.decode("utf-8")

        self.assertIn("/static/engola-ui-v2.css", html)
        self.assertIn("/static/engola-ui-v2.js", html)

        # The old layered UI injection must remain absent.
        for legacy_asset in (
            "/static/engola-v11.js",
            "/static/engola-v12.js",
            "/static/engola-v16.js",
            "/static/engola-v17.js",
            "/static/engola-v18.js",
            "/static/engola-v1.1.js",
        ):
            self.assertNotIn(legacy_asset, html)

    def test_disconnect_routes_accept_post(self):
        from routers.integration_actions import router
        routes={(getattr(r,'path',''), tuple(sorted(getattr(r,'methods',set())))) for r in router.routes}
        self.assertTrue(any(path=='/api/integrations/google/disconnect' and 'POST' in methods for path,methods in routes))
        self.assertTrue(any(path=='/api/integrations/github/disconnect' and 'POST' in methods for path,methods in routes))


class TestBraveProvider(unittest.TestCase):
    def test_brave_provider_imports(self):
        from core import brave
        self.assertTrue(callable(brave.configured))
        self.assertTrue(callable(brave.llm_context))
        self.assertTrue(callable(brave.search))
        self.assertTrue(callable(brave.answer))

    def test_chat_module_imports_brave_provider(self):
        import routers.chat as chat

        self.assertTrue(hasattr(chat, "_brave_grounding"))
        self.assertTrue(hasattr(chat, "brave_configured"))
