#!/usr/bin/env python3
"""WillTechBH IA Nexus Portable 3.0 — ponto de entrada.

Uso:
  python3 nexus3.py start       inicia motor + interface local
  python3 nexus3.py doctor      relatório de diagnóstico
  python3 nexus3.py setup --yes instala o motor verificado da plataforma
  python3 nexus3.py models      lista/recomenda/instala modelos
  python3 nexus3.py build       gera pacotes portáteis por plataforma
  python3 nexus3.py selftest    executa testes automatizados
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nexus3 import __version__  # noqa: E402
from nexus3.config import Config  # noqa: E402
from nexus3.engine import ENGINE_MANIFEST, EngineError  # noqa: E402
from nexus3.hardware import detect_hardware  # noqa: E402
from nexus3.models import installation_status  # noqa: E402
from nexus3.platform import detect_platform, find_root  # noqa: E402
from nexus3.server import NexusApp, run_server  # noqa: E402


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def cmd_doctor(args: argparse.Namespace) -> int:
    app = NexusApp(root=find_root(), start_engine=False)
    report = app.doctor()
    _print_json(report)
    return 0 if report["ok"] else 1


def cmd_setup(args: argparse.Namespace) -> int:
    root = find_root()
    config = Config.load(root)
    platform_info = detect_platform()
    hardware = detect_hardware(platform_info, root, config)
    manifest = ENGINE_MANIFEST.get(platform_info.engine_key)
    if not manifest:
        print("Plataforma sem binário oficial verificado.", file=sys.stderr)
        return 2
    print(f"Plataforma: {platform_info.system}/{platform_info.arch} ({platform_info.engine_key})")
    print(f"RAM detectada: {hardware.ram_total_gb:.1f} GB | perfil: {hardware.tier}")
    print(f"Arquivo: {manifest['file']} ({manifest['size'] / 1048576:.1f} MB)")
    print(f"SHA-256: {manifest['sha256']}")
    if not args.yes:
        print("\nNada foi baixado. Confirme com --yes para autorizar o download.")
        return 0
    config.set("downloads.allow_external", True)
    config.save()
    app = NexusApp(root=root, start_engine=False)
    try:
        binary = app.engine.ensure_binary(_progress)
    except PermissionError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 3
    print(f"\nMotor instalado e verificado: {binary.relative_to(root)}")
    return 0


def _progress(phase: str, done: int, total: int, message: str) -> None:
    if phase == "download" and total:
        pct = min(100, int(done * 100 / total))
        print(f"\r  {pct:3d}%  {message}", end="", flush=True)
    elif phase in ("verified", "start"):
        print(f"\n  {phase}: {message}")


def cmd_models(args: argparse.Namespace) -> int:
    root = find_root()
    app = NexusApp(root=root, start_engine=False)
    action = args.action or "list"
    if action == "list":
        for spec in app.registry.all():
            ok, verified = installation_status(root, spec)
            print(f"{spec.id:28s} {spec.name:34s} {spec.size_gb:5.2f} GB  "
                  f"instalado={'sim' if ok else 'nao'}  hash={'ok' if verified else '-'}")
        return 0
    if action == "recommend":
        spec, reason = app.registry.select(app.hardware)
        _print_json({"recommended": spec.id if spec else None, "reason": reason,
                     "hardware": app.hardware.to_dict()})
        return 0
    if action == "install":
        spec = app.registry.get(args.id or "")
        if not spec:
            print("Modelo inexistente. Use 'models list'.", file=sys.stderr)
            return 2
        print(f"Modelo: {spec.name} ({spec.size_gb:.2f} GB)")
        for item in spec.files:
            print(f"  {item.path}\n  SHA-256 {item.sha256}")
        if not args.yes:
            print("\nNada foi baixado. Confirme com --yes.")
            return 0
        app.config.set("downloads.allow_external", True)
        app.config.save()
        app.install_model(spec.id, _progress)
        print("Download verificado concluído.")
        return 0
    if action == "select":
        _print_json(app.select_model(args.id or ""))
        return 0
    return 2


def cmd_start(args: argparse.Namespace) -> int:
    root = find_root()
    app = NexusApp(root=root, start_engine=True)
    server = run_server(app, host="127.0.0.1", port=args.port or 0)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"WillTechBH IA Nexus {__version__} em {url}")
    print("O navegador recebe uma sessão local automaticamente.")
    print(f"Token para API/CLI (Authorization: Bearer ...): {app.api_key}")
    for error in app.startup_errors:
        print(f"AVISO: {error}", file=sys.stderr)
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando com segurança...")
    finally:
        server.server_close()
        app.engine.shutdown()
        app.web.enabled = False
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    import unittest

    root = find_root()
    suite = unittest.defaultTestLoader.discover(str(root / "nexus3" / "tests"), top_level_dir=str(root))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def cmd_build(args: argparse.Namespace) -> int:
    """Gera arquivos portáteis sem binários/modelos (download verificado no primeiro uso)."""
    import tarfile
    import zipfile

    root = find_root()
    out = root / "dist"
    try:
        out.mkdir(exist_ok=True)
    except FileExistsError:
        pass
    include = ("nexus3.py", "nexus3/", "config/", "scripts/", "docs/", "MANIFEST.json", "README.md", "CHANGELOG.md")
    exclude_dirs = {"__pycache__"}
    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d")

    def members():
        for pattern in include:
            path = root / pattern
            if path.is_file():
                yield path
            elif path.is_dir():
                for file in path.rglob("*"):
                    rel = file.relative_to(root)
                    if file.is_file() and not any(part in exclude_dirs for part in rel.parts[:-1]):
                        if file.suffix == ".pyc":
                            continue
                        # Configuração de runtime nunca é distribuída: ela pode
                        # conter autorização de download ou chave de API.
                        if rel.as_posix() == "config/nexus3.json":
                            continue
                        yield file

    windows = out / f"WillTechBH-IA-Nexus-3.0-win-portable-{stamp}.zip"
    with zipfile.ZipFile(windows, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in members():
            zf.write(file, Path("WillTechBH-IA-Nexus-3.0") / file.relative_to(root))
    unix = out / f"WillTechBH-IA-Nexus-3.0-unix-portable-{stamp}.tar.gz"
    with tarfile.open(unix, "w:gz") as tf:
        for file in members():
            tf.add(file, arcname=Path("WillTechBH-IA-Nexus-3.0") / file.relative_to(root))
    for artifact in (windows, unix):
        print(f"{artifact.name}: {artifact.stat().st_size / 1024:.0f} KB")
    print("Pacotes sem modelos/engines: o primeiro uso exige download autorizado.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nexus3.py", description="WillTechBH IA Nexus Portable 3.0")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="inicia a aplicação local")
    p_start.add_argument("--port", type=int, default=0)
    p_start.add_argument("--no-browser", action="store_true")
    p_start.set_defaults(func=cmd_start)

    p_doc = sub.add_parser("doctor", help="diagnóstica instalação e hardware")
    p_doc.set_defaults(func=cmd_doctor)

    p_setup = sub.add_parser("setup", help="instala o motor verificado")
    p_setup.add_argument("--yes", action="store_true", help="autoriza o download")
    p_setup.set_defaults(func=cmd_setup)

    p_models = sub.add_parser("models", help="gerencia modelos")
    p_models.add_argument("action", nargs="?", choices=["list", "recommend", "install", "select"])
    p_models.add_argument("id", nargs="?")
    p_models.add_argument("--yes", action="store_true", help="autoriza o download")
    p_models.set_defaults(func=cmd_models)

    p_build = sub.add_parser("build", help="gera pacotes portáteis")
    p_build.set_defaults(func=cmd_build)

    p_test = sub.add_parser("selftest", help="executa testes automatizados")
    p_test.set_defaults(func=cmd_selftest)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
