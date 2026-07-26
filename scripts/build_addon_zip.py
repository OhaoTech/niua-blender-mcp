"""Build the shippable Blender add-on zip: the product, without the policy layer.

The repo tree and the released add-on are deliberately not the same thing. What ships is
neutral Blender translation plus the measurement eyes; the opinionated half -- budgets,
gates, asset classes, and the retopo/LOD/collision recipes -- stays in the repo so the
benchmark can keep working on it, and is left out of the artifact until it is good enough
to stand behind.

Exclusion is by *absence*, not by a flag. ``domains/__init__.py`` discovers a domain by
the presence of its module, so a zip without ``domains/policy/`` is a Blender add-on in
which those tools do not exist -- nothing to disable, nothing to accidentally re-enable,
and CI can assert it by listing the archive.

Usage::

    python scripts/build_addon_zip.py                  # -> dist/niua_mcp_bridge-<ver>.zip
    python scripts/build_addon_zip.py --out /tmp/x.zip
    python scripts/build_addon_zip.py --include-policy  # dev build, everything

The zip roots every entry at ``niua_mcp_bridge/`` so it installs through Blender's
Preferences > Add-ons > Install... directly.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SOURCE = REPO / "blender_addon" / "niua_mcp_bridge"
PACKAGE = "niua_mcp_bridge"

#: Directories (relative to the add-on package root) kept out of the released add-on.
#: Each is a POLICY area -- see blender_addon/niua_mcp_bridge/domains/policy/__init__.py.
PRODUCT_EXCLUDE = (
    "domains/policy",  # feedback.quality/readiness/critique, asset_class.*, object.retopo & co
    "finishing",       # budgets, gates, engine/material/export profiles, preservation ledger
)

#: Never useful in any build.
ALWAYS_EXCLUDE = ("__pycache__",)


def _excluded(relative: pathlib.PurePosixPath, exclude: tuple[str, ...]) -> bool:
    parts = relative.parts
    if any(segment in ALWAYS_EXCLUDE for segment in parts):
        return True
    return any(relative == pathlib.PurePosixPath(e) or str(relative).startswith(e + "/")
               for e in exclude)


def product_files(source: pathlib.Path = SOURCE, *, include_policy: bool = False) -> list[pathlib.Path]:
    """Every file that belongs in the artifact, sorted, as paths relative to ``source``."""
    exclude = () if include_policy else PRODUCT_EXCLUDE
    out: list[pathlib.Path] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix == ".pyc":
            continue
        relative = pathlib.PurePosixPath(path.relative_to(source).as_posix())
        if not _excluded(relative, exclude):
            out.append(path.relative_to(source))
    return out


def addon_version(source: pathlib.Path = SOURCE) -> str:
    """``bl_info["version"]`` as a dotted string, for naming the archive."""
    text = (source / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'"version"\s*:\s*\(([^)]*)\)', text)
    if not match:
        return "0.0.0"
    return ".".join(part.strip() for part in match.group(1).split(","))


def build(out_path: pathlib.Path, *, include_policy: bool = False) -> tuple[int, list[str]]:
    files = product_files(include_policy=include_policy)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            archive.write(SOURCE / relative, arcname=str(pathlib.PurePosixPath(PACKAGE, relative.as_posix())))
    omitted = [str(p.relative_to(SOURCE)) for p in sorted(SOURCE.rglob("*"))
               if p.is_file() and p.suffix != ".pyc"
               and "__pycache__" not in p.parts
               and p.relative_to(SOURCE) not in set(files)]
    return len(files), omitted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=pathlib.Path, default=None, help="output zip path")
    parser.add_argument("--include-policy", action="store_true",
                        help="dev build: keep the policy layer in the archive")
    args = parser.parse_args(argv)

    version = addon_version()
    suffix = "-dev" if args.include_policy else ""
    out_path = args.out or (REPO / "dist" / f"{PACKAGE}-{version}{suffix}.zip")

    count, omitted = build(out_path, include_policy=args.include_policy)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"{out_path}  ({count} files, {size_kb:.0f} KB)")
    if omitted:
        print(f"  policy layer left out ({len(omitted)} files):")
        for name in omitted:
            print(f"    - {name}")
    else:
        print("  policy layer INCLUDED (dev build -- do not release this)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
