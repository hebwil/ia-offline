"""Testes de documentos, RAG, roteador, ferramentas e API HTTP."""

from __future__ import annotations

import base64
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexus3.agents import get_agent, list_agents  # noqa: E402
from nexus3.chat import ChatStore  # noqa: E402
from nexus3.config import Config  # noqa: E402
from nexus3.documents import DocumentExtractor, chunk_document  # noqa: E402
from nexus3.engine import ENGINE_MANIFEST, EngineManager  # noqa: E402
from nexus3.hardware import HardwareProfile, detect_hardware  # noqa: E402
from nexus3.models import ModelRegistry  # noqa: E402
from nexus3.platform import detect_platform  # noqa: E402
from nexus3.rag import DocumentStore, cosine, tokenize  # noqa: E402
from nexus3.router import NexusRouter, analyze, choose_agent  # noqa: E402
from nexus3.server import NexusApp, run_server  # noqa: E402
from nexus3.tools import ToolRuntime, calculator  # noqa: E402


class TempAppCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for folder in ("config", "data", "state", "logs", "nexus3/ui", "models", "workspace/uploads"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "config" / "models.json", self.root / "config" / "models.json")
        for name in ("index.html", "style.css", "app.js"):
            shutil.copy(ROOT / "nexus3" / "ui" / name, self.root / "nexus3" / "ui" / name)
        self.config = Config.load(self.root)
        self.hardware = HardwareProfile(
            os="darwin", arch="arm64", ram_total_gb=16, ram_available_gb=12,
            cpu_cores=8, vram_total_gb=0, accelerations=["metal"],
        )

    def tearDown(self):
        self.tmp.cleanup()


class TestDocuments(TempAppCase):
    def test_text_csv_docx_xlsx_extraction(self):
        extractor = DocumentExtractor(self.root)
        (self.root / "a.txt").write_text("Nexus portable funciona offline.", encoding="utf-8")
        self.assertIn("offline", extractor.extract_path("a.txt").text)

        (self.root / "b.csv").write_text("nome,valor\nA,10\nB,20\n", encoding="utf-8")
        doc = extractor.extract_path("b.csv")
        self.assertIn("nome", doc.text)
        self.assertIn("20", doc.text)

        docx = self.root / "c.docx"
        with zipfile.ZipFile(docx, "w") as zf:
            zf.writestr("word/document.xml",
                        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                        '<w:body><w:p><w:r><w:t>Contrato de teste</w:t></w:r></w:p>'
                        '<w:p><w:r><w:t>Clausula segunda</w:t></w:r></w:p></w:body></w:document>')
        self.assertIn("Clausula segunda", extractor.extract_path("c.docx").text)

        xlsx = self.root / "d.xlsx"
        with zipfile.ZipFile(xlsx, "w") as zf:
            zf.writestr("xl/sharedStrings.xml",
                        '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                        '<si><t>Produto</t></si><si><t>Cafe</t></si></sst>')
            zf.writestr("xl/worksheets/sheet1.xml",
                        '<?xml version="1.0"?><ws xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                        '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row>'
                        '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>42</v></c></row></sheetData></ws>')
        self.assertIn("Cafe", extractor.extract_path("d.xlsx").text)

    def test_pdf_extraction_with_generated_fixture(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=200)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        })
        resources = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        page[NameObject("/Resources")] = writer._add_object(resources)
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 14 Tf 20 170 Td (Contrato PDF de teste Nexus) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
        path = self.root / "contrato.pdf"
        with path.open("wb") as handle:
            writer.write(handle)
        doc = DocumentExtractor(self.root).extract_path("contrato.pdf")
        self.assertIn("Nexus", doc.text)
        self.assertEqual(doc.page_count, 1)

    def test_image_without_ocr_does_not_invent_text(self):
        image = self.root / "captura.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        doc = DocumentExtractor(self.root).extract_path("captura.png")
        self.assertEqual(doc.text, "")
        self.assertTrue(any("não" in w or "visão" in w for w in doc.warnings))

    def test_chunking_preserves_pages(self):
        from nexus3.documents import Document

        doc = Document("x.txt", "x.txt", "text", "a" * 3000, 2, [], ["a" * 1500, "b" * 1500])
        chunks = list(chunk_document(doc, chunk_chars=500, overlap=50))
        self.assertGreater(len(chunks), 4)
        self.assertEqual({c.page for c in chunks}, {1, 2})


class TestRAG(TempAppCase):
    def test_tokenize_and_cosine(self):
        self.assertEqual(tokenize("A cláusula contratual, nos autos!"), ["clausula", "contratual", "autos"])
        self.assertAlmostEqual(cosine([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(cosine([1, 0], [0, 1]), 0.0)

    def test_index_search_and_citations(self):
        from nexus3.documents import Document

        store = DocumentStore(self.root, self.config)
        doc = Document("contrato.txt", "workspace/uploads/contrato.txt", "text",
                       "Cláusula 1: o prazo é de 30 dias.\n\nCláusula 2: a multa é de 2%.",
                       page_count=0, pages=["Cláusula 1: prazo de 30 dias.", "Cláusula 2: multa de 2%."])
        count = store.index_document(doc)
        self.assertEqual(count, 2)
        results = store.search("prazo de 30 dias")
        self.assertTrue(results)
        self.assertEqual(results[0].doc_name, "contrato.txt")
        self.assertEqual(results[0].page, 1)
        prompt = store.grounded_prompt("qual o prazo?", results, "Responda em pt-BR")
        self.assertIn("FONTE 1", prompt)
        self.assertIn("Inferência do modelo", prompt)
        self.assertIn("qual o prazo?", prompt)
        saved = DocumentStore(self.root, self.config)
        self.assertEqual(len(saved.chunks), 2)
        self.assertEqual(saved.remove_document("workspace/uploads/contrato.txt"), 2)


class TestRouterAndTools(unittest.TestCase):
    def test_analyze_detects_domains(self):
        code = analyze("Escreva um script Python para corrigir este bug", [])
        legal = analyze("Analise a petição e a CLT sobre rescisão", [])
        self.assertTrue(code.needs_code)
        self.assertTrue(legal.needs_legal)
        self.assertGreater(legal.complexity, code.complexity * 0.5)
        self.assertEqual(choose_agent(legal, "automatico"), "advogado")
        self.assertEqual(choose_agent(code, "automatico"), "programador")
        self.assertEqual(choose_agent(analyze("olá"), "automatico"), "geral")

    def test_router_decision_is_explainable(self):
        root = ROOT
        registry = ModelRegistry(root)
        hardware = HardwareProfile(os="darwin", arch="arm64", ram_total_gb=16,
                                   ram_available_gb=12, vram_total_gb=0)
        config = Config.load(root)
        decision = NexusRouter(registry, hardware, config).route(
            "Explique passo a passo este contrato e a CLT", agent_id="automatico"
        )
        self.assertIn(decision.model_id, registry.models)
        self.assertTrue(decision.rationale)
        self.assertGreater(decision.context, 0)
        self.assertGreater(decision.estimated_seconds, 0)
        self.assertFalse(decision.needs_web)
        self.assertLessEqual(decision.temperature, 0.7)

    def test_agents_cover_required_specialists(self):
        ids = {a["id"] for a in list_agents()}
        self.assertTrue({"programador", "advogado", "tecnico", "escritor", "analista",
                         "pesquisador", "imagem"}.issubset(ids))
        self.assertTrue(get_agent("inexistente").id == "geral")

    def test_calculator_is_safe_and_deterministic(self):
        self.assertEqual(calculator("(2+3)*4"), "20")
        self.assertIn("inválida", calculator("__import__('os').system('echo oi')"))
        self.assertIn("não permitida", calculator("[1,2][0]"))

    def test_tools_respect_allowlist(self):
        config = Config.load(ROOT)
        config.set("tools.enabled", True)
        runtime = ToolRuntime(config)
        self.assertEqual(len(runtime.definitions()), 2)
        self.assertIn("não autorizada", runtime.call("exec_shell_command", {}))


class TestEngineManifest(unittest.TestCase):
    def test_all_targets_have_verified_engine_hashes(self):
        expected = {"win-cpu-x64", "win-cpu-arm64", "macos-arm64", "macos-x64", "ubuntu-x64", "ubuntu-arm64"}
        self.assertTrue(expected.issubset(ENGINE_MANIFEST))
        for key, item in ENGINE_MANIFEST.items():
            self.assertEqual(len(item["sha256"]), 64, key)

    def test_build_command_uses_localhost_and_api_key(self):
        root = ROOT
        platform_info = detect_platform()
        hardware = detect_hardware(platform_info, root)
        config = Config.load(root)
        manager = EngineManager(root, platform_info, hardware, config)
        from nexus3.models import ModelRegistry

        spec = ModelRegistry(root).get("qwen3-4b-q4")
        cmd = manager.build_command(
            Path("llama-server"), spec, Path("model.gguf"), 9931, 4096, 0, "abc123"
        )
        self.assertIn("127.0.0.1", cmd)
        self.assertIn("--api-key", cmd)
        self.assertIn("-c", cmd)
        self.assertNotIn("--tools", cmd)


class TestHTTPAPI(TempAppCase):
    def setUp(self):
        super().setUp()
        self.app = NexusApp(root=self.root, start_engine=False)
        self.server = run_server(self.app, port=0)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=6) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def post(self, path, payload):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_health_status_and_static_ui(self):
        status, health = self.get("/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        _, status_data = self.get("/api/status")
        self.assertEqual(status_data["version"], "3.0.0-develop")
        self.assertFalse(status_data["online_active"])
        with urllib.request.urlopen(self.base + "/", timeout=6) as response:
            self.assertIn("Nexus Studio 3.0", response.read().decode("utf-8"))

    def test_openai_compatible_models(self):
        _, data = self.get("/v1/models")
        self.assertEqual(data["object"], "list")
        self.assertEqual(len(data["data"]), 1)

    def test_upload_documents_index_and_search(self):
        payload = base64.b64encode("Prazo de 45 dias para contestar.".encode("utf-8")).decode("ascii")
        _, uploaded = self.post("/api/upload", {"name": "notas.txt", "kind": "text", "content": payload})
        self.assertTrue(uploaded["ok"])
        self.assertGreater(uploaded["chunks"], 0)
        _, docs = self.get("/api/docs")
        self.assertEqual(len(docs["documents"]), 1)
        _, results = self.get("/api/docs/search?q=prazo%20de%2045%20dias")
        self.assertTrue(results["results"])
        self.assertIn("notas.txt", results["results"][0]["doc_name"])

    def test_chat_history_endpoints(self):
        _, new = self.post("/api/new_chat", {})
        self.assertTrue(new["ok"])
        _, history = self.get("/api/history")
        self.assertTrue(history["chats"])
        sid = history["active"]
        _, loaded = self.get("/api/history/load?id=" + sid)
        self.assertEqual(loaded["messages"], [])
        _, deleted = self.post("/api/history/delete", {"id": sid})
        self.assertTrue(deleted["ok"])

    def test_doctor_reports_real_state_without_engine(self):
        _, report = self.get("/api/doctor")
        names = {c["name"] for c in report["checks"]}
        self.assertIn("motor instalado", names)
        self.assertFalse(next(c["ok"] for c in report["checks"] if c["name"] == "motor instalado"))

    def test_offline_is_default_and_online_requires_opt_in(self):
        _, status = self.get("/api/status")
        self.assertFalse(status["online_active"])
        self.assertTrue(self.app.config.get("privacy.online_opt_in_required"))

    def test_chat_without_engine_returns_explicit_error(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/chat", {"message": "olá"})
        self.assertEqual(ctx.exception.code, 503)
        result = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertFalse(result["ok"])
        self.assertTrue(result["engine_dead"])
        self.assertIn("motor", result["error"].lower())

    def test_download_requires_authorization(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/models/install", {"id": "qwen3-4b-q4"})
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
