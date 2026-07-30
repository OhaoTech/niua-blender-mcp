#!/usr/bin/env python3
"""Install Niua Blender Finisher as a Blender *extension* (not a legacy add-on).

Legacy path (outdated):
  scripts/install_addon.py  →  ~/.config/blender/<ver>/scripts/addons/niua_mcp_bridge

Current path (this script):
  blender --command extension build
  blender --command extension install-file --repo user_default --enable
  → bl_ext.user_default.niua_blender_finisher

Product name: **Niua Blender Finisher**
Source tree (import path): blender_addon/niua_mcp_bridge/  (stable internal package name)

Usage::

    python scripts/install_extension.py
    python scripts/install_extension.py --blender /path/to/blender
    python scripts/install_extension.py --include-policy   # dev: full tree
    python scripts/install_extension.py --uninstall
    python scripts/install_extension.py --no-remove-legacy
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(REPO, "blender_addon", "niua_mcp_bridge")
EXT_ID = "niua_blender_finisher"
LEGACY_EXT_IDS = ("niua_mcp_bridge", "niua_blender_finisher")
LEGACY_ADDON_DIRNAMES = ("niua_mcp_bridge", "niua_blender_finisher")
MODULE = f"bl_ext.user_default.{EXT_ID}"
PRODUCT_NAME = "Niua Blender Finisher"


def find_blender(explicit: str | None) -> str | None:
    if explicit:
        return explicit if (os.path.isfile(explicit) or shutil.which(explicit)) else None
    return shutil.which("blender")


def run(cmd: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def legacy_addons_dir(blender: str) -> str | None:
    begin, end = "<<<NIUA_ADDONS:", ":NIUA_ADDONS>>>"
    query = (
        "import bpy,sys;"
        f"sys.stdout.write('{begin}' + "
        "bpy.utils.user_resource('SCRIPTS', path='addons', create=True)"
        f" + '{end}\\n')"
    )
    try:
        proc = run([blender, "--background", "--factory-startup", "--python-expr", query], timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = proc.stdout or ""
    if begin in out and end in out:
        path = out.split(begin, 1)[1].split(end, 1)[0].strip()
        return path or None
    return None


def remove_legacy(blender: str) -> None:
    root = legacy_addons_dir(blender)
    if not root:
        print("legacy add-ons dir: (could not resolve — skip)")
        return
    for name in LEGACY_ADDON_DIRNAMES:
        target = os.path.join(root, name)
        if os.path.islink(target):
            os.unlink(target)
            print(f"removed legacy symlink {target}")
        elif os.path.isdir(target):
            shutil.rmtree(target)
            print(f"removed legacy add-on {target}")
        else:
            print(f"no legacy install at {target}")


def uninstall_extension(blender: str) -> int:
    for ext_id in LEGACY_EXT_IDS:
        proc = run(
            [blender, "--background", "--online-mode", "--command", "extension", "remove", ext_id],
            timeout=180,
        )
        print((proc.stdout or "")[-500:])
        if proc.stderr:
            print(proc.stderr[-500:], file=sys.stderr)
    return 0


def build_extension_zip(blender: str, source_dir: str, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    proc = run(
        [
            blender, "--background", "--command", "extension", "build",
            f"--source-dir={source_dir}",
            f"--output-dir={out_dir}",
            "--valid-tags=",
        ],
        timeout=180,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"extension build failed (exit {proc.returncode})")
    print((proc.stdout or "").strip())
    zips = [
        os.path.join(out_dir, name)
        for name in os.listdir(out_dir)
        if name.endswith(".zip") and EXT_ID in name
    ]
    if not zips:
        # any zip
        zips = [os.path.join(out_dir, n) for n in os.listdir(out_dir) if n.endswith(".zip")]
    if not zips:
        raise SystemExit(f"no zip produced in {out_dir}")
    zips.sort(key=os.path.getmtime, reverse=True)
    return zips[0]


def stage_source(*, include_policy: bool) -> tuple[str, tempfile.TemporaryDirectory[str] | None]:
    """Return (source_dir, tmp_or_None). Product builds strip policy/finishing."""
    if include_policy:
        return SOURCE, None
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    from build_addon_zip import product_files  # noqa: PLC0415

    tmp = tempfile.TemporaryDirectory(prefix="niua_ext_")
    dest = os.path.join(tmp.name, EXT_ID)
    os.makedirs(dest, exist_ok=True)
    # manifest always
    for name in ("blender_manifest.toml",):
        src = os.path.join(SOURCE, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest, name))
    for relative in product_files():
        src = os.path.join(SOURCE, str(relative))
        out = os.path.join(dest, str(relative))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copy2(src, out)
    # ensure manifest present even if product_files skipped it
    manifest_src = os.path.join(SOURCE, "blender_manifest.toml")
    if os.path.isfile(manifest_src):
        shutil.copy2(manifest_src, os.path.join(dest, "blender_manifest.toml"))
    return dest, tmp


def install_file(blender: str, zip_path: str) -> None:
    proc = run(
        [
            blender, "--background", "--online-mode",
            "--command", "extension", "install-file",
            zip_path,
            "--repo", "user_default",
            "--enable",
        ],
        timeout=300,
    )
    print((proc.stdout or "").strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    if proc.returncode != 0:
        raise SystemExit(f"extension install-file failed (exit {proc.returncode})")


def verify(blender: str) -> bool:
    expr = (
        "import bpy\n"
        f"keys = list(bpy.context.preferences.addons.keys())\n"
        f"mod = '{MODULE}'\n"
        "print('ADDON_KEYS', [k for k in keys if 'niua' in k.lower() or 'mcp' in k.lower()])\n"
        "print('ENABLED', mod in keys)\n"
        "try:\n"
        f"    m = __import__(mod)\n"
        "    print('IMPORT_OK', getattr(m, '__file__', m))\n"
        "except Exception as e:\n"
        "    print('IMPORT_ERR', e)\n"
    )
    proc = run(
        [blender, "--background", "--online-mode", "--python-expr", expr],
        timeout=180,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out[-1500:])
    return "ENABLED True" in out or "IMPORT_OK" in out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blender", default=None)
    ap.add_argument("--include-policy", action="store_true",
                    help="install full repo tree (policy + finishing) for local dev")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--no-remove-legacy", action="store_true",
                    help="keep scripts/addons/niua_mcp_bridge if present")
    ap.add_argument("--keep-zip", action="store_true", help="copy built zip to dist/")
    args = ap.parse_args(argv)

    if not os.path.isfile(os.path.join(SOURCE, "blender_manifest.toml")):
        print(f"error: missing blender_manifest.toml in {SOURCE}", file=sys.stderr)
        return 2

    blender = find_blender(args.blender)
    if blender is None:
        print("error: no blender binary on PATH", file=sys.stderr)
        return 2
    print(f"product: {PRODUCT_NAME}")
    print(f"blender: {blender}")

    if args.uninstall:
        if not args.no_remove_legacy:
            remove_legacy(blender)
        uninstall_extension(blender)
        print("done (uninstall)")
        return 0

    if not args.no_remove_legacy:
        remove_legacy(blender)

    # remove previous extension installs (old + new id)
    uninstall_extension(blender)

    source_dir, tmp = stage_source(include_policy=args.include_policy)
    try:
        with tempfile.TemporaryDirectory(prefix="niua_ext_out_") as out_dir:
            zip_path = build_extension_zip(blender, source_dir, out_dir)
            print(f"built: {zip_path} ({os.path.getsize(zip_path)} bytes)")
            if args.keep_zip:
                dist = os.path.join(REPO, "dist")
                os.makedirs(dist, exist_ok=True)
                dest = os.path.join(dist, os.path.basename(zip_path))
                shutil.copy2(zip_path, dest)
                print(f"copied zip → {dest}")
            install_file(blender, zip_path)
    finally:
        if tmp is not None:
            tmp.cleanup()

    ok = verify(blender)
    print()
    if ok:
        print(f"OK: {PRODUCT_NAME} enabled as {MODULE}")
    else:
        print("WARN: install finished but verify did not see the module enabled")
        print(f"  Open Blender → Preferences → Extensions → enable '{PRODUCT_NAME}'")
    print("Next:")
    print("  1. blender --online-mode   (GUI) → N-panel → Niua → Start Finisher :8765")
    print("  2. MCP host: python -m niua_blender_mcp  (Grok: blender-finisher)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
