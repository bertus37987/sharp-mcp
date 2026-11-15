from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sharp_mcp import cli, plugin_installer
from sharp_mcp.blender_installer import _execute_bpy_via_socket


class TestBaselineCompatibility(unittest.TestCase):
    def test_doctor_server_import_compatibility(self) -> None:
        for error in (None, ModuleNotFoundError("mcp.server.fastmcp was removed")):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as td:
                args = cli.build_parser().parse_args(["doctor", "--json", "--project-dir", td])
                output = io.StringIO()
                with patch.object(cli.importlib, "import_module", side_effect=error), contextlib.redirect_stdout(output):
                    status = cli._cmd_doctor(args)
                result = json.loads(output.getvalue())
                self.assertEqual(status, 0 if error is None else 1)
                self.assertEqual(result["ok"], error is None)
                self.assertEqual(result["python"]["server_importable"], error is None)
                self.assertTrue(result["python"]["all_dependencies_present"])
                if error:
                    self.assertIn("mcp>=1.7.0,<2", result["python"]["server_import_error"])
                else:
                    self.assertIsNone(result["python"]["server_import_error"])

    def test_plugin_package_resource_fallback(self) -> None:
        class ResourcePath:
            def __init__(self, path: Path) -> None:
                self.path = path

            def joinpath(self, child: str) -> ResourcePath:
                return ResourcePath(self.path / child)

            def __str__(self) -> str:
                return str(self.path)

        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            with patch.object(plugin_installer, "__file__", str(Path(td) / "absent" / "plugin_installer.py")), patch.object(
                plugin_installer.importlib.resources, "files", side_effect=lambda package: ResourcePath(root / package)
            ):
                source = plugin_installer.get_plugin_source_path()
            self.assertTrue(source.is_file())
            self.assertEqual(source.name, plugin_installer.PLUGIN_FILENAME)
            self.assertIn(b"<roblox", source.read_bytes())

    def test_socket_empty_invalid_and_chunked_responses(self) -> None:
        cases = [
            ([b""], False),
            ([b"{", b""], False),
            ([b"[]"], False),
            ([b'{"status": "success",', b'"result": {"result": "OK"}}'], True),
        ]
        for chunks, expected_ok in cases:
            with self.subTest(chunks=chunks):
                sock = MagicMock()
                sock.recv.side_effect = chunks
                with patch("sharp_mcp.blender_installer.socket.create_connection") as connect:
                    connect.return_value.__enter__.return_value = sock
                    result = _execute_bpy_via_socket("print('ok')", "localhost", 9876, 1.0)
                self.assertEqual(result["ok"], expected_ok)
                if expected_ok:
                    self.assertEqual(result["stdout"], "OK")
                else:
                    self.assertEqual(result["code"], "INVALID_SOCKET_RESPONSE")

    def test_animation_sampling_requires_blender(self) -> None:
        script = Path(__file__).resolve().parents[1] / "sharp_mcp" / "bundled_skills" / "roblox-animation" / "scripts" / "blender_bake_to_roblox.py"
        spec = importlib.util.spec_from_file_location("sharp_bake_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, "bpy", None), patch.object(module, "matrix_to_roblox_cf", None):
            with self.assertRaisesRegex(RuntimeError, "Blender bpy"):
                module.bake_clip(None, "Test", start_frame=1, end_frame=2)
