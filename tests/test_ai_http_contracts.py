from __future__ import annotations

# Provider response schemas: https://ai.google.dev/api/generate-content and
# https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion

import asyncio
import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import aiohttp
from PIL import Image

from sharp_mcp.ai_http import AIRequestError, post_json
from sharp_mcp.credentials_store import MODEL_PRESETS
from sharp_mcp.domain_engines.art_creation_engine import ArtCreationEngine
from sharp_mcp.domain_engines.design_engine import DesignEngine
from sharp_mcp.domain_engines.gui_engine import GuiDomainEngine
from sharp_mcp.domain_engines.multimodal_qa_engine import MultimodalQAEngine


KEY = "mock-provider-key-not-real"
GEMINI = "https://generativelanguage.googleapis.com"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"


class _Response:
    def __init__(self, data=None, *, status=200, headers=None):
        self.status = status
        self.headers = headers or {}
        self.raw = data if isinstance(data, str) else json.dumps(data or {})

    async def text(self):
        return self.raw

    async def json(self):
        return json.loads(self.raw)

    async def read(self):
        return self.raw.encode()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class _Session:
    def __init__(self):
        self.post = mock.Mock()
        self.get = mock.Mock()
        self.delete = mock.Mock(return_value=_Response())

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


def _text_response(provider, text='{"verdict":"SHIP"}'):
    if provider == "gemini":
        return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}]}
    return {"choices": [{"message": {"role": "assistant", "content": [{"type": "text", "text": text}]}, "finish_reason": "stop"}]}


def _route(provider, role="image_gen"):
    return {"provider": provider, "planned_provider": provider, "model": MODEL_PRESETS[provider][role]["default"], "key_configured": True, "api_key": KEY}


class TestAIHttpContracts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = _Session()
        self.patch = mock.patch("aiohttp.ClientSession", return_value=self.session)
        self.factory = self.patch.start()
        self.addCleanup(self.patch.stop)
        self.qa = MultimodalQAEngine()
        skills = Path(__file__).resolve().parents[1] / "sharp_mcp" / "bundled_skills"
        self.art = ArtCreationEngine(design_engine=DesignEngine(), gui_engine=GuiDomainEngine(skills))

    def assert_auth(self, call, provider):
        headers = call.kwargs["headers"]
        if provider == "gemini":
            self.assertEqual(headers["x-goog-api-key"], KEY)
        else:
            self.assertEqual(headers["Authorization"], f"Bearer {KEY}")
            self.assertIn("HTTP-Referer", headers)
            self.assertIn("X-Title", headers)
        self.assertNotIn(KEY, call.args[0])
        self.assertNotIn("?key=", call.args[0])
        self.assertEqual(headers["Content-Type"], "application/json")

    async def test_gemini_inline_media_request_and_response(self):
        with tempfile.TemporaryDirectory() as td:
            for mime in ("video/mp4", "audio/wav"):
                with self.subTest(mime=mime):
                    path = Path(td) / "media"
                    path.write_bytes(b"media fixture")
                    self.session.post.return_value = _Response(_text_response("gemini"))
                    result = await self.qa._upload_and_analyze_gemini_file(
                        api_key=KEY, model="gemini-2.5-flash", file_path=path, mime_type=mime, prompt_text="Inspect it",
                    )
                    self.assertTrue(result["ok"])
                    self.assertEqual(result["parsed_json"], {"verdict": "SHIP"})
                    call = self.session.post.call_args
                    self.assertEqual(call.args[0], GEMINI + "/v1beta/models/gemini-2.5-flash:generateContent")
                    self.assert_auth(call, "gemini")
                    self.assertEqual(call.kwargs["json"], {
                        "contents": [{"role": "user", "parts": [
                            {"inlineData": {"mimeType": mime, "data": base64.b64encode(b"media fixture").decode()}},
                            {"text": "Inspect it"},
                        ]}],
                        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
                    })
                    self.assertEqual(self.factory.call_args.kwargs["timeout"].total, 120)

    async def test_openrouter_image_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "hud.png"
            path.write_bytes(b"png fixture")
            self.session.post.return_value = _Response(_text_response("openrouter"))
            result = await self.qa._call_openrouter_vision(api_key=KEY, model="google/gemini-2.5-flash", image_paths=[path], prompt_text="Inspect")
            self.assertTrue(result["ok"])
            self.assertEqual(result["parsed_json"], {"verdict": "SHIP"})
            call = self.session.post.call_args
            self.assertEqual(call.args[0], OPENROUTER)
            self.assert_auth(call, "openrouter")
            self.assertEqual(call.kwargs["json"], {
                "model": "google/gemini-2.5-flash", "temperature": 0.2,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": "Inspect"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,cG5nIGZpeHR1cmU="}},
                ]}],
            })

    async def test_ui_concept_requests_and_empty_response_fallback(self):
        art = self.art
        for provider in ("gemini", "openrouter"):
            route = _route(provider, "gui_code")
            with self.subTest(provider=provider), mock.patch("sharp_mcp.domain_engines.art_creation_engine.resolve_provider_and_model", return_value=route):
                self.session.post.return_value = _Response(_text_response(provider))
                result = await art.generate_ui_concept()
                self.assertTrue(result["ai_generation"]["ok"])
                self.assertEqual(result["generation_mode"], "ai_assisted")
                call = self.session.post.call_args
                self.assert_auth(call, provider)
                body = call.kwargs["json"]
                if provider == "gemini":
                    self.assertEqual(call.args[0], GEMINI + f"/v1beta/models/{route['model']}:generateContent")
                    self.assertEqual(body["generationConfig"], {"temperature": 0.35, "responseMimeType": "application/json"})
                    self.assertEqual(body["contents"][0]["role"], "user")
                    self.assertTrue(body["contents"][0]["parts"][0]["text"])
                else:
                    self.assertEqual(call.args[0], OPENROUTER)
                    self.assertEqual(set(body), {"model", "temperature", "messages"})
                    self.assertEqual([m["role"] for m in body["messages"]], ["system", "user"])
                self.assertEqual(self.factory.call_args.kwargs["timeout"].total, 90)
                self.session.post.return_value = _Response({})
                result = await art.generate_ui_concept()
                self.assertFalse(result["ai_generation"]["ok"])
                self.assertEqual(result["generation_mode"], "offline_deterministic_blueprint")

    async def test_image_generation_requests_and_doc_response_paths(self):
        buf = io.BytesIO()
        Image.new("RGB", (2, 2)).save(buf, format="PNG")
        png = buf.getvalue()
        encoded = base64.b64encode(png).decode()
        with tempfile.TemporaryDirectory() as td:
            for provider in ("gemini", "openrouter"):
                route = _route(provider)
                with self.subTest(provider=provider), mock.patch("sharp_mcp.domain_engines.art_creation_engine.resolve_provider_and_model", return_value=route):
                    response = _text_response(provider)
                    if provider == "gemini":
                        response["candidates"][0]["content"]["parts"] = [{"inlineData": {"mimeType": "image/png", "data": encoded}}]
                    else:
                        response["choices"][0]["message"]["images"] = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}}]
                    self.session.post.return_value = _Response(response)
                    result = await self.art.generate_ai_art(subject="A golden shield", auto_slice=False, output_dir=td)
                    self.assertTrue(result["ok"])
                    self.assertEqual(Path(result["raw_image_path"]).read_bytes(), png)
                    call = self.session.post.call_args
                    self.assert_auth(call, provider)
                    if provider == "gemini":
                        self.assertEqual(call.args[0], GEMINI + f"/v1beta/models/{route['model']}:generateContent")
                        self.assertEqual(call.kwargs["json"], {"contents": [{"role": "user", "parts": [{"text": "A golden shield"}]}], "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}})
                    else:
                        self.assertEqual(call.args[0], OPENROUTER)
                        self.assertEqual(call.kwargs["json"], {"model": route["model"], "modalities": ["image", "text"], "messages": [{"role": "user", "content": "A golden shield"}]})
                    self.assertEqual(self.factory.call_args.kwargs["timeout"].total, 120)
                    for empty in ({}, _text_response(provider)):
                        self.session.post.return_value = _Response(empty)
                        failed = await self.art.generate_ai_art(auto_slice=False, output_dir=td)
                        self.assertFalse(failed["ok"])

    async def test_empty_blocked_truncated_and_error_responses(self):
        fixtures = [
            ("gemini", {"promptFeedback": {"blockReason": "SAFETY"}}),
            ("gemini", {"candidates": []}),
            ("gemini", {"candidates": [{"finishReason": "SAFETY"}]}),
            ("gemini", {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "partial"}]}}]}),
            ("openrouter", {"choices": []}),
            ("openrouter", {"choices": [{"finish_reason": "content_filter", "message": {"content": "partial"}}]}),
            ("openrouter", {"error": {"code": 503, "message": "provider failed " + KEY}}),
        ]
        for provider, data in fixtures:
            with self.subTest(data=data):
                self.session.post.return_value = _Response(data)
                if provider == "gemini":
                    result = await self.qa._call_gemini_generate(api_key=KEY, model="model", parts=[])
                else:
                    result = await self.qa._call_openrouter_vision(api_key=KEY, model="model", image_paths=[], prompt_text="inspect")
                self.assertFalse(result["ok"])
                self.assertNotIn(KEY, json.dumps(result))

    async def test_http_json_and_transport_errors_never_echo_keys(self):
        for response in (_Response("unauthorized ?key=" + KEY, status=401), _Response("not json"), _Response("[]")):
            with self.subTest(response=response.raw):
                self.session.post.return_value = response
                result = await self.qa._call_gemini_generate(api_key=KEY, model="model", parts=[])
                self.assertFalse(result["ok"])
                self.assertNotIn(KEY, json.dumps(result))
        for exc in (asyncio.TimeoutError(), aiohttp.ClientError("secret URL ?key=" + KEY)):
            with self.subTest(exc=type(exc).__name__):
                self.session.post.side_effect = exc
                result = await self.qa._call_gemini_generate(api_key=KEY, model="model", parts=[])
                self.assertFalse(result["ok"])
                self.assertNotIn(KEY, json.dumps(result))

    async def test_inline_request_limit_and_retired_imagen(self):
        result = await self.qa._call_gemini_generate(api_key=KEY, model="model", parts=[{"text": "x" * 20_000_001}])
        self.assertFalse(result["ok"])
        self.session.post.assert_not_called()
        route = {**_route("gemini"), "model": "imagen-3.0-generate-002"}
        with tempfile.TemporaryDirectory() as td, mock.patch("sharp_mcp.domain_engines.art_creation_engine.resolve_provider_and_model", return_value=route):
            result = await self.art.generate_ai_art(output_dir=td)
            self.assertFalse(result["ok"])
            self.assertIn("shut down", result["error"])
            self.session.post.assert_not_called()

    async def test_file_upload_lifecycle_success_failure_and_timeout_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "video.mp4"
            with path.open("wb") as stream:
                stream.truncate(11 * 1024 * 1024)
            for state in ("ACTIVE", "FAILED", "PROCESSING", "HTTP_ERROR", "BAD_JSON"):
                with self.subTest(state=state), mock.patch("asyncio.sleep", new_callable=mock.AsyncMock):
                    self.session.post.reset_mock()
                    self.session.delete.reset_mock()
                    self.session.post.side_effect = [
                        _Response(headers={"x-goog-upload-url": "https://upload.example/session"}),
                        _Response({"file": {"name": "files/123", "uri": GEMINI + "/v1beta/files/123", "state": "PROCESSING"}}),
                        _Response(_text_response("gemini")),
                    ]
                    self.session.get.return_value = _Response(
                        "bad json" if state == "BAD_JSON" else ({"state": state} if state != "HTTP_ERROR" else "failed " + KEY),
                        status=403 if state == "HTTP_ERROR" else 200,
                    )
                    result = await self.qa._upload_and_analyze_gemini_file(api_key=KEY, model="gemini-2.5-flash", file_path=path, mime_type="video/mp4", prompt_text="inspect")
                    self.assertEqual(result["ok"], state == "ACTIVE")
                    self.assertNotIn(KEY, json.dumps(result))
                    calls = self.session.post.call_args_list
                    self.assertEqual(calls[0].args[0], GEMINI + "/upload/v1beta/files")
                    self.assertEqual(calls[0].kwargs["json"], {"file": {"display_name": "video.mp4"}})
                    h = calls[0].kwargs["headers"]
                    self.assertEqual(h["x-goog-api-key"], KEY)
                    self.assertEqual(h["X-Goog-Upload-Protocol"], "resumable")
                    self.assertEqual(h["X-Goog-Upload-Header-Content-Type"], "video/mp4")
                    self.assertEqual(h["X-Goog-Upload-Header-Content-Length"], str(path.stat().st_size))
                    self.assertEqual(calls[1].kwargs["headers"]["X-Goog-Upload-Command"], "upload, finalize")
                    self.assertEqual(calls[1].args[0], "https://upload.example/session")
                    self.assertEqual(calls[1].kwargs["headers"]["X-Goog-Upload-Offset"], "0")
                    self.assertEqual(len(calls[1].kwargs["data"]), path.stat().st_size)
                    self.session.delete.assert_called_once_with(GEMINI + "/v1beta/files/123", headers={"x-goog-api-key": KEY})
                    self.session.get.assert_called_with(GEMINI + "/v1beta/files/123", headers={"x-goog-api-key": KEY})
                    if state == "ACTIVE":
                        self.assertEqual(calls[2].kwargs["json"]["contents"][0]["parts"][0], {"fileData": {"mimeType": "video/mp4", "fileUri": GEMINI + "/v1beta/files/123"}})
                    else:
                        self.assertEqual(len(calls), 2)

    async def test_shared_http_error_contract(self):
        self.session.post.return_value = _Response({"error": {"message": "failed " + KEY}})
        with self.assertRaises(AIRequestError) as caught:
            await post_json(OPENROUTER, headers={}, payload={}, api_key=KEY, timeout_sec=15)
        self.assertNotIn(KEY, str(caught.exception))

    async def test_image_errors_are_structured_and_redacted(self):
        with tempfile.TemporaryDirectory() as td:
            for provider in ("gemini", "openrouter"):
                with self.subTest(provider=provider), mock.patch("sharp_mcp.domain_engines.art_creation_engine.resolve_provider_and_model", return_value=_route(provider)):
                    self.session.post.return_value = _Response("provider rejected " + KEY, status=400)
                    result = await self.art.generate_ai_art(auto_slice=False, output_dir=td)
                    self.assertFalse(result["ok"])
                    self.assertIn("HTTP 400", result["error"])
                    self.assertNotIn(KEY, json.dumps(result))
                    data = _text_response(provider)
                    if provider == "gemini":
                        data["candidates"][0]["content"]["parts"] = [{"inlineData": {"mimeType": "image/png", "data": "not base64!"}}]
                    else:
                        data["choices"][0]["message"]["images"] = [{"image_url": {"url": "data:image/png;base64,not base64!"}}]
                    self.session.post.return_value = _Response(data)
                    result = await self.art.generate_ai_art(auto_slice=False, output_dir=td)
                    self.assertFalse(result["ok"])
                    self.assertIn("base64", result["error"])
