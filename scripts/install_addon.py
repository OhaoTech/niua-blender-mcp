#!/usr/bin/env python3
"""Install the Blender add-on into Blender's user add-ons directory.

    python scripts/install_addon.py                 # symlink (edits apply live)
    python scripts/install_addon.py --copy          # copy instead of symlink
    python scripts/install_addon.py --blender /path/to/blender
    python scripts/install_addon.py --uninstall

Blender is asked where its own add-ons directory is (``bpy.utils.user_resource``)
rather than guessing per-platform paths, so this works on Linux/macOS/Windows and
across Blender versions. Prints exactly what it did and what to do next; every
failure mode is reported rather than raising a traceback.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(REPO, "blender_addon", "niua_mcp_bridge")
PACKAGE = "niua_mcp_bridge"

# Delimit BOTH ends: Blender writes its version banner to stdout without a leading
# newline, so a bare "KEY=<path>" line gets the banner glued onto the end of the path.
_BEGIN, _END = "<<<NIUA_ADDONS:", ":NIUA_ADDONS>>>"
_QUERY = (
    "import bpy,sys;"
    f"sys.stdout.write('{_BEGIN}' + "
    "bpy.utils.user_resource('SCRIPTS', path='addons', create=True)"
    f" + '{_END}\\n')"
)


def find_blender(explicit: str | None) -> str | None:
    if explicit:
        return explicit if (os.path.isfile(explicit) or shutil.which(explicit)) else None
    return shutil.which("blender")


def addons_dir(blender: str) -> tuple[str | None, str]:
    """Ask Blender for its user add-ons directory. Returns (path, detail)."""
    try:
        run = subprocess.run(
            [blender, "--background", "--factory-startup", "--python-expr", _QUERY],
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return None, "blender did not respond within 180s"
    except OSError as exc:
        return None, f"could not run blender: {exc}"
    out = run.stdout or ""
    if _BEGIN in out and _END in out:
        path = out.split(_BEGIN, 1)[1].split(_END, 1)[0].strip()
        if path:
            return path, "resolved via bpy.utils.user_resource"
    tail = ((run.stderr or out).strip().splitlines() or ["no output"])[-1]
    return None, f"blender did not report a path ({tail})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Install the Niua MCP Bridge Blender add-on.")
    ap.add_argument("--blender", default=None, help="path to the blender binary (default: from PATH)")
    ap.add_argument("--copy", action="store_true", help="copy files instead of symlinking")
    ap.add_argument("--uninstall", action="store_true", help="remove a previous install")
    ap.add_argument("--product", action="store_true",
                    help="install exactly what users get: the pure MCP, without the "
                         "policy layer (implies --copy, since a symlink would drag it in)")
    args = ap.parse_args(argv)

    if not os.path.isdir(SOURCE):
        print(f"error: add-on source not found: {SOURCE}", file=sys.stderr)
        return 2

    blender = find_blender(args.blender)
    if blender is None:
        print("error: no `blender` binary found. Install Blender 4.0+ or pass --blender /path/to/blender",
              file=sys.stderr)
        return 2

    target_root, detail = addons_dir(blender)
    if target_root is None:
        print(f"error: could not locate Blender's add-ons directory -- {detail}", file=sys.stderr)
        return 2
    target = os.path.join(target_root, PACKAGE)

    if args.uninstall:
        if os.path.islink(target):
            os.unlink(target)
        elif os.path.isdir(target):
            shutil.rmtree(target)
        else:
            print(f"nothing to remove at {target}")
            return 0
        print(f"removed {target}")
        return 0

    if os.path.islink(target):
        os.unlink(target)
    elif os.path.isdir(target):
        shutil.rmtree(target)

    if args.product:
        # Copy only the files the release artifact contains, so what runs in Blender is
        # the same surface a user installs -- the point being to catch a policy import
        # that the repo tree would silently satisfy.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from build_addon_zip import product_files  # noqa: PLC0415

        for relative in product_files():
            dest = os.path.join(target, str(relative))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(os.path.join(SOURCE, str(relative)), dest)
        how = "copied WITHOUT the policy layer (product install)"
    elif args.copy:
        shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        how = "copied"
    else:
        try:
            os.symlink(SOURCE, target, target_is_directory=True)
            how = "symlinked (edits in the repo apply immediately)"
        except OSError as exc:  # Windows without developer mode, odd filesystems
            shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            how = f"copied (symlink unavailable: {exc})"

    ok = os.path.isfile(os.path.join(target, "__init__.py"))
    print(f"add-on {how}")
    print(f"  from : {SOURCE}")
    print(f"  to   : {target}")
    print(f"  check: __init__.py present = {ok}  ({detail})")
    if not ok:
        print("error: install looks incomplete", file=sys.stderr)
        return 1
    print()
    print("Next:")
    print("  NOTE: legacy add-on install is outdated. Prefer:")
    print("    python scripts/install_extension.py --include-policy")
    print("  1. Preferences → Extensions → enable 'Niua Blender Finisher'")
    print("  2. N-panel → Niua → Start Finisher (127.0.0.1:8765)")
    print("  3. Verify:  python scripts/bridge_call.py 8765 system.health '{}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
