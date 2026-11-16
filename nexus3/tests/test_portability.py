"""Testes de portabilidade que rodam em qualquer SO (sem hardware real).

Cobrem: mapeamento plataforma->engine_key, estrutura dos launchers,
resolucao de raiz por variavel de ambiente, seguranca de extracao de
arquivos e integridade de URLs do manifesto. Sao executados na matriz
de CI (Windows/macOS/Linux) e localmente. NAO substituem homologacao
em hardware real — veja docs/CONTINUIDADE.md.
"""

from __future__ import annotations

import io
import os
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexus3.engine import ENGINE_MANIFEST, ENGINE_URL_TEMPLATE, _safe_extract_archive  # noqa: E402
from nexus3.models import ModelRegistry  # noqa: E402
from nexus3.platform import PlatformInfo, find_root, portable_path  # noqa: E402


SCRIPTS = ROOT / "scripts"


class TestPlatformMapping(unittest.TestCase):
    def test_engine_key_for_every_supported_platform(self):
        cases = [
            ("windows", "x64", "win-cpu-x64"),
            ("windows", "arm64", "win-cpu-arm64"),
            ("darwin", "arm64", "macos-arm64"),
            ("darwin", "x64", "macos-x64"),
            ("linux", "x64", "ubuntu-x64"),
            ("linux", "arm64", "ubuntu-arm64"),
        ]
        for system, arch, expected in cases:
            info = PlatformInfo(
                system=system, machine=arch, arch=arch,
                exe_suffix=".exe" if system == "windows" else "",
                python="3.10", raw_system=system,
            )
            self.assertEqual(info.engine_key, expected, f"{system}/{arch}")
            self.assertIn(expected, ENGINE_MANIFEST)

    def test_engine_urls_are_https_and_use_build(self):
        for key, item in ENGINE_MANIFEST.items():
            url = ENGINE_URL_TEMPLATE.format(
                build="b12444", file=item["file"]
            )
            self.assertTrue(url.startswith("https://"), key)
            self.assertIn("b12444", url)
            self.assertIn(item["file"], url)


class TestLaunchers(unittest.TestCase):
    def test_all_launchers_exist(self):
        for name in ("start-windows.bat", "start-macos.command", "start-linux.sh", "doctor.sh"):
            self.assertTrue((SCRIPTS / name).is_file(), name)

    @unittest.skipIf(os.name == "nt", "bits de execucao nao se aplicam ao Windows")
    def test_posix_launchers_are_executable(self):
        for name in ("start-macos.command", "start-linux.sh", "doctor.sh"):
            self.assertTrue(os.access(SCRIPTS / name, os.X_OK), name)

    def test_posix_launchers_use_relative_root_and_version_check(self):
        for name in ("start-macos.command", "start-linux.sh"):
            text = (SCRIPTS / name).read_text(encoding="utf-8")
            self.assertIn('$(dirname "$0")/..', text)
            self.assertIn("NEXUS3_ROOT", text)
            self.assertIn("version_info", text, f"{name} sem checagem de versao")

    def test_windows_launcher_uses_relative_root_and_version_check(self):
        text = (SCRIPTS / "start-windows.bat").read_text(encoding="utf-8")
        self.assertIn('cd /d "%~dp0.."', text)
        self.assertIn("NEXUS3_ROOT", text)
        self.assertIn("py -3", text)
        self.assertIn("version_info", text)

    def test_launchers_do_not_hardcode_host_paths(self):
        for name in ("start-windows.bat", "start-macos.command", "start-linux.sh"):
            text = (SCRIPTS / name).read_text(encoding="utf-8")
            self.assertNotIn("/Users/", text)
            self.assertNotIn("/home/", text)
            self.assertNotIn("C:\\Users", text)


class TestRootResolution(unittest.TestCase):
    def test_find_root_prefers_env(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "nexus3.py"
            marker.write_text("# marker", encoding="utf-8")
            previous = os.environ.get("NEXUS3_ROOT")
            os.environ["NEXUS3_ROOT"] = folder
            try:
                self.assertEqual(find_root(ROOT), Path(folder).resolve())
            finally:
                if previous is None:
                    os.environ.pop("NEXUS3_ROOT", None)
                else:
                    os.environ["NEXUS3_ROOT"] = previous

    def test_portable_path_handles_windows_style_parts(self):
        with tempfile.TemporaryDirectory() as folder:
            result = portable_path(folder, "models", "nano", "model.gguf")
            expected = (Path(folder) / "models" / "nano" / "model.gguf").resolve()
            self.assertEqual(result, expected)
            self.assertTrue(result.is_relative_to(Path(folder).resolve()))


class TestArchiveExtractionSafety(unittest.TestCase):
    def test_tar_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "evil.tar.gz"
            with tarfile.open(archive, "w:gz") as tf:
                data = b"x"
                info = tarfile.TarInfo("../outside.txt")
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            with self.assertRaises(ValueError):
                _safe_extract_archive(archive, Path(folder) / "dest")

    def test_zip_absolute_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "evil.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("/absolute/evil.txt", b"x")
            with self.assertRaises(ValueError):
                _safe_extract_archive(archive, Path(folder) / "dest")


class TestModelURLs(unittest.TestCase):
    def test_all_model_files_use_https_and_have_hash(self):
        registry = ModelRegistry(ROOT)
        for spec in registry.all():
            for item in spec.files:
                self.assertTrue(item.url.startswith("https://"), item.url)
                self.assertEqual(len(item.sha256), 64, spec.id)
                self.assertGreater(item.size, 0, spec.id)


if __name__ == "__main__":
    unittest.main()
