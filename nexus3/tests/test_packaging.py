"""Testes dos pacotes Lite e Offline Complete e da atualizacao preservadora.

Usa raizes temporarias sinteticas — nao depende de motor/modelo baixados e
nao duplica arquivos grandes. Valida estrutura, seguranca e preservacao.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexus3.packaging import (  # noqa: E402
    CODE_INCLUDE, PACKAGE_ROOT, PROFILE_LITE, PROFILE_OFFLINE,
    PackageError, apply_update, build_lite, installed_models,
    ready_offline_platforms,
)


def make_minimal_root(base: Path) -> Path:
    """Cria uma arvore de codigo minima para empacotamento de teste."""
    for folder in ("nexus3/ui", "nexus3/tests", "config", "scripts", "docs"):
        (base / folder).mkdir(parents=True, exist_ok=True)
    (base / "nexus3.py").write_text("# entry\n", encoding="utf-8")
    (base / "nexus3" / "__init__.py").write_text("", encoding="utf-8")
    (base / "nexus3" / "ui" / "index.html").write_text("<html></html>", encoding="utf-8")
    (base / "config" / "models.json").write_text('{"models":[]}', encoding="utf-8")
    (base / "config" / "nexus3.json").write_text('{"server":{"api_key":"SEGREDO"}}', encoding="utf-8")
    (base / "MANIFEST.json").write_text("{}", encoding="utf-8")
    (base / "README.md").write_text("teste", encoding="utf-8")
    (base / "CHANGELOG.md").write_text("teste", encoding="utf-8")
    (base / "scripts" / "start-linux.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (base / "docs" / "LIMITACOES.md").write_text("teste", encoding="utf-8")
    return base


class TestBuildLite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_minimal_root(Path(self.tmp.name))
        self.out = self.root / "dist"

    def tearDown(self):
        self.tmp.cleanup()

    def test_lite_builds_both_formats_with_manifest(self):
        artifacts = build_lite(self.root, self.out)
        self.assertEqual(len(artifacts), 2)
        zip_path = next(p for p in artifacts if p.name.endswith(".zip"))
        tar_path = next(p for p in artifacts if p.name.endswith(".tar.gz"))
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            self.assertIn(f"{PACKAGE_ROOT}/nexus3.py", names)
            self.assertIn(f"{PACKAGE_ROOT}/PACKAGE.json", names)
            payload = json.loads(zf.read(f"{PACKAGE_ROOT}/PACKAGE.json"))
            self.assertEqual(payload["profile"], PROFILE_LITE)
        with tarfile.open(tar_path, "r:gz") as tf:
            names = tf.getnames()
            self.assertIn(f"{PACKAGE_ROOT}/PACKAGE.json", names)

    def test_lite_excludes_runtime_config_and_pyc(self):
        artifacts = build_lite(self.root, self.out)
        zip_path = next(p for p in artifacts if p.name.endswith(".zip"))
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            self.assertFalse(any(n.endswith("config/nexus3.json") for n in names))
            self.assertFalse(any(n.endswith(".pyc") for n in names))
            # O segredo da config de runtime nao pode vazar no pacote.
            for n in names:
                if n.endswith(".json"):
                    self.assertNotIn(b"SEGREDO", zf.read(n))


class TestOfflineReadiness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_engine_means_no_offline_platforms(self):
        self.assertEqual(ready_offline_platforms(self.root), [])
        self.assertEqual(installed_models(self.root), [])

    def test_offline_build_refuses_without_verified_runtime(self):
        from nexus3.packaging import build_offline
        with self.assertRaises(PackageError):
            build_offline(self.root, self.root / "dist")


class TestApplyUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = make_minimal_root(self.base / "source")
        self.install = self.base / "install"
        self.install.mkdir()
        (self.install / "nexus3.py").write_text("# antigo", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _package(self) -> Path:
        return build_lite(self.source, self.base / "dist")[0]

    def test_update_replaces_code_and_preserves_runtime(self):
        # Estado do usuario que NAO pode ser perdido.
        (self.install / "data" / "chats").mkdir(parents=True)
        (self.install / "data" / "chats" / "chat.json").write_text("MEUS DADOS", encoding="utf-8")
        (self.install / "models" / "nano").mkdir(parents=True)
        (self.install / "models" / "nano" / "m.gguf").write_bytes(b"MODELO")
        (self.install / "config").mkdir()
        (self.install / "config" / "nexus3.json").write_text("CHAVE", encoding="utf-8")
        (self.install / "state").mkdir()
        (self.install / "state" / "install-id.txt").write_text("ID", encoding="utf-8")

        result = apply_update(self._package(), self.install)
        self.assertTrue(result["ok"])
        self.assertIn("nexus3.py", result["replaced"])
        self.assertIn("# entry", (self.install / "nexus3.py").read_text())
        self.assertEqual((self.install / "data/chats/chat.json").read_text(), "MEUS DADOS")
        self.assertEqual((self.install / "models/nano/m.gguf").read_bytes(), b"MODELO")
        self.assertEqual((self.install / "config/nexus3.json").read_text(), "CHAVE")
        self.assertEqual((self.install / "state/install-id.txt").read_text(), "ID")

    def test_update_rejects_invalid_package(self):
        fake = self.base / "fake.zip"
        with zipfile.ZipFile(fake, "w") as zf:
            zf.writestr("random.txt", "x")
        with self.assertRaises(PackageError):
            apply_update(fake, self.install)


if __name__ == "__main__":
    unittest.main()
