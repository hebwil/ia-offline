"""Testes de plataforma, configuração, segurança, hardware e modelos."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexus3.config import Config, DEFAULTS  # noqa: E402
from nexus3.hardware import HardwareProfile, context_recommendation, gpu_layers_recommendation  # noqa: E402
from nexus3.models import DownloadManager, ModelRegistry, installation_status, sha256_file  # noqa: E402
from nexus3.platform import detect_platform, find_root, portable_path  # noqa: E402
from nexus3.security import AtomicWriter, PathGuard, ProcessRegistry, redact  # noqa: E402


class TempRootCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for folder in ("config", "data", "state", "logs", "nexus3/ui", "models"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "config" / "models.json", self.root / "config" / "models.json")

    def tearDown(self):
        self.tmp.cleanup()


class TestPlatformAndSecurity(TempRootCase):
    def test_platform_detects_current_os_and_arch(self):
        info = detect_platform()
        self.assertIn(info.system, ("windows", "darwin", "linux"))
        self.assertIn(info.arch, ("x64", "arm64", "other"))
        self.assertTrue(info.engine_key)

    def test_find_root_uses_marker(self):
        self.assertEqual(find_root(ROOT), ROOT)

    def test_portable_path_rejects_traversal(self):
        with self.assertRaises(ValueError):
            portable_path(self.root, "../fora.txt")
        with self.assertRaises(ValueError):
            portable_path(self.root, "data", "..", "..", "etc")

    def test_path_guard_relative(self):
        guard = PathGuard(self.root)
        path = guard.resolve("data", "chats", "a.json")
        self.assertEqual(guard.relative(path), "data/chats/a.json")

    def test_redaction_removes_secrets_and_user_paths(self):
        text = "key sk-abcdefghijkl1234 Bearer eyJhbGciOiJIUzI1NiJ9 /Users/will/doc.txt"
        clean = redact(text)
        self.assertNotIn("sk-abcdefghijkl1234", clean)
        self.assertNotIn("/Users/will", clean)
        self.assertIn("REDACTADO", clean)

    def test_atomic_writer_creates_backup(self):
        writer = AtomicWriter(self.root)
        writer.write_json("config/test.json", {"v": 1})
        writer.write_json("config/test.json", {"v": 2})
        backups = list((self.root / "data" / "backups").glob("test-*.json"))
        self.assertTrue(backups)
        self.assertEqual(json.loads(backups[0].read_text())["v"], 1)
        self.assertEqual(json.loads((self.root / "config" / "test.json").read_text())["v"], 2)

    def test_process_registry_never_owns_unregistered_pid(self):
        registry = ProcessRegistry()
        self.assertFalse(registry.owns(os.getpid()))
        self.assertFalse(registry.stop(os.getpid()))
        self.assertEqual(registry.snapshot(), [])


class TestConfig(TempRootCase):
    def test_defaults_load_and_roundtrip(self):
        config = Config.load(self.root)
        self.assertEqual(config.get("defaults.mode"), "offline")
        self.assertTrue(config.get("privacy.local_only_by_default"))
        config.set("server.port", 8123)
        config.save()
        self.assertEqual(Config.load(self.root).get("server.port"), 8123)
        self.assertNotIn("***", json.dumps(DEFAULTS))

    def test_public_view_hides_api_key(self):
        config = Config.load(self.root)
        config.set("server.api_key", "super-segredo")
        self.assertEqual(config.public_view()["server"]["api_key"], "***")


class TestHardware(unittest.TestCase):
    def test_tiers_and_budgets(self):
        modest = HardwareProfile(os="linux", arch="x64", ram_total_gb=4, ram_available_gb=3)
        advanced = HardwareProfile(os="darwin", arch="arm64", ram_total_gb=32,
                                   ram_available_gb=24, vram_total_gb=16)
        self.assertEqual(modest.tier, "modest")
        self.assertEqual(advanced.tier, "advanced")
        self.assertLess(modest.budget_gb, advanced.budget_gb)
        self.assertEqual(gpu_layers_recommendation(modest), 0)
        self.assertEqual(gpu_layers_recommendation(advanced), 999)
        self.assertLessEqual(context_recommendation(modest, 32768), 8192)


class TestModels(TempRootCase):
    def test_registry_has_verified_hashes(self):
        registry = ModelRegistry(self.root)
        self.assertGreaterEqual(len(registry.all()), 6)
        for spec in registry.all():
            for item in spec.files:
                self.assertEqual(len(item.sha256), 64, f"{spec.id}: hash inválido")

    def test_installation_status_without_files(self):
        registry = ModelRegistry(self.root)
        spec = registry.get("qwen3-4b-q4")
        ok, verified = installation_status(self.root, spec)
        self.assertFalse(ok)
        self.assertFalse(verified)

    def test_installation_status_detects_tampering(self):
        registry = ModelRegistry(self.root)
        spec = registry.get("qwen3-4b-q4")
        target = self.root / spec.files[0].path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"modelo falso")
        ok, verified = installation_status(self.root, spec)
        self.assertTrue(ok)
        self.assertFalse(verified)

    def test_selection_respects_capabilities_and_ram(self):
        registry = ModelRegistry(self.root)
        small = HardwareProfile(os="linux", arch="x64", ram_total_gb=4, ram_available_gb=3)
        spec, reason = registry.select(small, {"chat"}, "text")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.id, "qwen3-0.6b-q8")
        self.assertIn("prioridade", reason)
        spec2, _ = registry.select(small, {"vision"}, "text")
        self.assertIsNone(spec2)

    def test_download_manager_verifies_hash_and_resumes(self):
        payload = b"conteudo verificavel do modelo\n" * 500
        digest = hashlib.sha256(payload).hexdigest()
        prefix = payload[:5000]

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get("Range"):
                    start = int(self.headers["Range"].split("=")[1].split("-")[0])
                    body = payload[start:]
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{len(payload)-1}/{len(payload)}")
                else:
                    body = payload
                    self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            from nexus3.models import ModelFile

            target_dir = self.root / "models" / "test"
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "fake.gguf.part").write_bytes(prefix)
            item = ModelFile(
                path="models/test/fake.gguf",
                url=f"http://127.0.0.1:{server.server_port}/model.gguf",
                sha256=digest, size=len(payload),
            )
            config = Config.load(self.root)
            config.set("downloads.allow_external", True)
            manager = DownloadManager(self.root, config)
            events = []
            result = manager.download_file(item, lambda *args: events.append(args[0]), key="t")
            self.assertEqual(result.read_bytes(), payload)
            self.assertEqual(sha256_file(result), digest)
            self.assertIn("start", events)
            self.assertIn("verified", events)
            self.assertFalse((target_dir / "fake.gguf.part").exists())
        finally:
            server.shutdown()
            server.server_close()

    def test_download_rejects_bad_hash(self):
        from nexus3.models import ModelFile

        payload = b"conteudo original"
        server = ThreadingHTTPServer(("127.0.0.1", 0), type(
            "H", (BaseHTTPRequestHandler,), {
                "do_GET": lambda self: (
                    self.send_response(200), self.send_header("Content-Length", str(len(payload))),
                    self.end_headers(), self.wfile.write(payload)
                ),
                "log_message": lambda self, *a: None,
            }))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            item = ModelFile(
                path="models/test/bad.gguf",
                url=f"http://127.0.0.1:{server.server_port}/x",
                sha256="0" * 64, size=len(payload),
            )
            config = Config.load(self.root)
            config.set("downloads.allow_external", True)
            with self.assertRaises(ValueError):
                DownloadManager(self.root, config).download_file(item, key="bad")
            self.assertFalse((self.root / "models/test/bad.gguf").exists())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
