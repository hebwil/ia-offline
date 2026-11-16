"""Construcao dos pacotes Nexus Lite e Nexus Offline Complete.

Principios:
- Lite: codigo + UI + scripts + documentacao. Sem motor/modelo. O primeiro
  uso obtem componentes verificados mediante autorizacao explicita.
- Offline Complete: codigo + motor + pelo menos um modelo verificado. Nenhum
  acesso a rede apos a preparacao. Somente construido para plataformas cujos
  binarios E modelos ja estao presentes e verificados localmente.
- Atualizacao: substitui apenas arquivos de codigo. NUNCA toca em data/,
  state/, logs/, workspace/, config/nexus3.json, models/ ou bin/engines/.
- Symlinks de dylib sao preservados (tar.gz em Unix), conforme exigido pelo
  motor llama.cpp no macOS.
- Arquivos sao escritos DIRETAMENTE nos arquivos a partir da fonte (sem
  copiar para staging), evitando duplicar modelos de centenas de MB.
"""

from __future__ import annotations

import io
import json
import shutil
import tarfile
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .engine import ENGINE_MANIFEST, _safe_extract_archive
from .models import ModelRegistry, ModelSpec, installation_status, sha256_file

PACKAGE_ROOT = "WillTechBH-IA-Nexus-3.0"
PROFILE_LITE = "lite"
PROFILE_OFFLINE = "offline-complete"

CODE_INCLUDE = (
    "nexus3.py", "nexus3/", "config/models.json", "scripts/", "docs/",
    "MANIFEST.json", "README.md", "CHANGELOG.md",
)
CODE_EXCLUDE_DIRS = {"__pycache__"}
CODE_EXCLUDE_FILES = {"config/nexus3.json"}

# Diretorios de estado que uma atualizacao JAMAIS sobrescreve.
PRESERVE_DIRS = ("data", "state", "logs", "workspace", "models", "bin")
PRESERVE_FILES = ("config/nexus3.json",)


class PackageError(RuntimeError):
    pass


def _code_files(root: Path) -> Iterable[Path]:
    for pattern in CODE_INCLUDE:
        path = root / pattern
        if path.is_file():
            yield path
        elif path.is_dir():
            for file in path.rglob("*"):
                rel = file.relative_to(root)
                if not file.is_file():
                    continue
                if any(part in CODE_EXCLUDE_DIRS for part in rel.parts[:-1]):
                    continue
                if rel.as_posix() in CODE_EXCLUDE_FILES:
                    continue
                if file.suffix == ".pyc":
                    continue
                yield file


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d")


def _manifest_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _arcname(root: Path, file: Path) -> str:
    return f"{PACKAGE_ROOT}/{file.relative_to(root).as_posix()}"


def _write_zip(path: Path, entries: list[tuple[str, Path | bytes]]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, source in entries:
            if isinstance(source, bytes):
                zf.writestr(arcname, source)
            else:
                zf.write(source, arcname)


def _write_tar(path: Path, entries: list[tuple[str, Path | bytes]]) -> None:
    with tarfile.open(path, "w:gz", compresslevel=1) as tf:
        for arcname, source in entries:
            if isinstance(source, bytes):
                info = tarfile.TarInfo(arcname)
                info.size = len(source)
                info.mtime = int(datetime.now().timestamp())
                tf.addfile(info, io.BytesIO(source))
            elif source.is_symlink():
                info = tf.gettarinfo(source, arcname=arcname)
                info.linkname = str(source.readlink())
                tf.addfile(info)
            else:
                tf.add(source, arcname=arcname, recursive=False)


def build_lite(root: Path, out_dir: Path | None = None) -> list[Path]:
    """Pacotes leves, independentes de plataforma (codigo puro Python)."""
    root = Path(root).resolve()
    out = out_dir or (root / "dist")
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(_code_files(root))
    if not files:
        raise PackageError("Nenhum arquivo de codigo encontrado para empacotar.")

    payload = {
        "profile": PROFILE_LITE,
        "version": "3.0.0-develop",
        "generated": datetime.now().isoformat(timespec="seconds"),
        "requires": "Python 3.10+ no host ou runtime portatil em runtime/python",
        "contains": {"code": True, "engine": False, "model": False},
        "first_run": "python3 nexus3.py setup --yes  (motor) e models install <id> --yes  (modelo)",
        "network_after_prep": "opcional — modo online e desativado por padrao",
        "files": len(files),
    }
    entries = [(_arcname(root, f), f) for f in files]
    entries.append((f"{PACKAGE_ROOT}/PACKAGE.json", _manifest_bytes(payload)))

    stamp = _stamp()
    artifacts: list[Path] = []
    zip_path = out / f"Nexus-Lite-3.0-all-{stamp}.zip"
    _write_zip(zip_path, entries)
    artifacts.append(zip_path)
    tar_path = out / f"Nexus-Lite-3.0-all-{stamp}.tar.gz"
    _write_tar(tar_path, entries)
    artifacts.append(tar_path)
    return artifacts


def installed_models(root: Path) -> list[ModelSpec]:
    registry = ModelRegistry(root)
    result = []
    for spec in registry.all():
        present, verified = installation_status(root, spec)
        if present and verified:
            result.append(spec)
    return result


def ready_offline_platforms(root: Path) -> list[dict[str, Any]]:
    """Plataformas com motor verificado E pelo menos um modelo verificado."""
    root = Path(root).resolve()
    result = []
    for key, manifest in ENGINE_MANIFEST.items():
        engine_dir = root / "bin" / "engines" / key
        binary_name = "llama-server.exe" if key.startswith("win-") else "llama-server"
        binaries = list(engine_dir.rglob(binary_name)) if engine_dir.exists() else []
        if not binaries:
            continue
        marker = root / "state" / f"engine-{key}-sha256.txt"
        verified = False
        if marker.is_file():
            try:
                expected = marker.read_text(encoding="ascii").strip().lower()
                verified = bool(expected) and sha256_file(binaries[0]) == expected
            except OSError:
                verified = False
        if not verified:
            continue
        result.append({
            "key": key,
            "engine_dir": engine_dir,
            "binary": binaries[0],
            "engine_sha256": sha256_file(binaries[0]),
            "models": installed_models(root),
        })
    return result


def build_offline(
    root: Path,
    out_dir: Path | None = None,
    platform_key: str | None = None,
    model_id: str | None = None,
) -> list[Path]:
    """Pacote Offline Complete para UMA plataforma com binarios verificados.

    Levanta PackageError se nao ha motor verificado ou modelo verificado para
    a plataforma — nunca produz um pacote 'offline' que exigira download.
    """
    root = Path(root).resolve()
    platforms = ready_offline_platforms(root)
    if platform_key:
        platforms = [p for p in platforms if p["key"] == platform_key]
    if not platforms:
        raise PackageError(
            "Nenhuma plataforma com motor verificado e modelo verificado localmente. "
            "Execute 'nexus3.py setup --yes' e 'models install <id> --yes' antes."
        )

    out = out_dir or (root / "dist")
    out.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    code_entries = [(_arcname(root, f), f) for f in sorted(_code_files(root))]
    artifacts: list[Path] = []

    for plat in platforms:
        key = plat["key"]
        models = plat["models"]
        if model_id:
            models = [m for m in models if m.id == model_id]
        if not models:
            if model_id:
                raise PackageError(f"Modelo {model_id} nao esta instalado e verificado para {key}.")
            continue

        entries = list(code_entries)
        # Motor: arvore inteira (symlinks relativos preservados no tar).
        for item in sorted(plat["engine_dir"].rglob("*")):
            rel = item.relative_to(root)
            entries.append((_arcname(root, item), item))

        # Marker de verificacao do motor.
        marker_data = (plat["engine_sha256"] + "\n").encode("ascii")
        entries.append((f"{PACKAGE_ROOT}/state/engine-{key}-sha256.txt", marker_data))

        # Modelos verificados: verifica hash novamente antes de incluir.
        model_hashes: dict[str, str] = {}
        for spec in models:
            for item in spec.files:
                source = root / item.path
                digest = sha256_file(source)
                if digest != item.sha256.lower():
                    raise PackageError(f"Hash divergente ao incluir {item.path}")
                model_hashes[item.path] = digest
                entries.append((_arcname(root, source), source))

        payload = {
            "profile": PROFILE_OFFLINE,
            "version": "3.0.0-develop",
            "generated": datetime.now().isoformat(timespec="seconds"),
            "platform": key,
            "requires": "Nenhum download: motor e modelo ja inclusos e verificados",
            "contains": {"code": True, "engine": True, "model": True},
            "network_after_prep": "nao necessario (modo online desativado por padrao)",
            "engine": {
                "key": key,
                "path": str(plat["binary"].relative_to(root)),
                "sha256": plat["engine_sha256"],
            },
            "models": [m.id for m in models],
            "model_files": model_hashes,
            "first_run": "Execute o launcher da plataforma; o motor inicia automaticamente.",
        }
        entries.append((f"{PACKAGE_ROOT}/PACKAGE.json", _manifest_bytes(payload)))

        if key.startswith("win-"):
            path = out / f"Nexus-Offline-Complete-3.0-{key}-{stamp}.zip"
            _write_zip(path, entries)
        else:
            path = out / f"Nexus-Offline-Complete-3.0-{key}-{stamp}.tar.gz"
            _write_tar(path, entries)
        artifacts.append(path)

    return artifacts


def apply_update(package: Path, install_root: Path) -> dict[str, Any]:
    """Atualiza o codigo a partir de um pacote, preservando todo o estado local.

    Nunca apaga diretorios: apenas substitui arquivos de codigo conhecidos.
    """
    package = Path(package).resolve()
    install_root = Path(install_root).resolve()
    with tempfile.TemporaryDirectory(prefix="nexus3-update-") as tmp:
        staging = Path(tmp)
        _safe_extract_archive(package, staging / "pkg")
        candidates = list((staging / "pkg").rglob(PACKAGE_ROOT))
        source_root = candidates[0] if candidates else (staging / "pkg")
        if not (source_root / "nexus3.py").is_file():
            raise PackageError("Pacote sem nexus3.py — nao e um pacote Nexus 3.0 valido.")
        replaced: list[str] = []
        for rel in CODE_INCLUDE:
            src = source_root / rel
            dst = install_root / rel
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                replaced.append(rel)
            elif src.is_dir():
                for file in src.rglob("*"):
                    if not file.is_file():
                        continue
                    sub = file.relative_to(src)
                    target = dst / sub
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, target)
                    replaced.append((Path(rel) / sub).as_posix())
        return {
            "ok": True,
            "replaced": replaced,
            "preserved_dirs": list(PRESERVE_DIRS),
            "preserved_files": list(PRESERVE_FILES),
        }
