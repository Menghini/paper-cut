#!/usr/bin/env python3
"""Convert Tower of Trials (jdaster64/ttyd-tot) into a Paper Cut code mod.

Rerunnable from a clean checkout, as docs/MODDING.md ("Porting a GameCube
mod") describes for the Practice Codes and the TTYD AP mod:

  1. fetch ToT at the pinned commit (or use --tot DIR, a checkout)
  2. copy its mod source (ttyd-tools/rel) to mods/tower-of-trials/tot/
  3. port/pause_extra.py                (ToT's re-laid-out pause menu fields: a struct of its own)
     tools/port/mod_fields.py --apply   (struct fields onto the decomp's names)
  4. port/designators.py                (the same, in data tables' .field = ...)
  5. tools/port/mod_headers.py          (ToT's game headers become shims)
  6. tools/port/mod_asm_stubs.py        (PowerPC .s routines become stubs)
  7. port/include/patch.h over ToT's    (hooks through Paper Cut's slots)
  8. port/manual.py                     (the hand-ported edits, exact text)
     port/byvalue.py                    (struct-by-address calls onto by-value prototypes)
  9. port/inventory.py                  (INVENTORY.md: what is left to hook)

  python mods/tower-of-trials/port/port_tot.py [--tot DIR] [--build build-pc-us-aurora]

The converted tree (tot/) is ToT's own source, GPL-3.0, generated and not
committed; what is committed is this pipeline and the hand-written port.
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(MOD))
TOOLS = os.path.join(ROOT, "tools", "port")

TOT_REPO = "https://github.com/jdaster64/ttyd-tot.git"
TOT_COMMIT = "245473f7d4574c75f51b5fd1b7ea0af1ea9a7465"  # v4.01 r62, 2026-03-11


def run(cmd, cwd=None):
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def fetch(dest):
    if not os.path.isdir(os.path.join(dest, ".git")):
        run(["git", "clone", "--filter=blob:none", TOT_REPO, dest])
    run(["git", "-C", dest, "fetch", "--depth", "1", "origin", TOT_COMMIT])
    run(["git", "-C", dest, "checkout", "--detach", TOT_COMMIT])


def aliases():
    out = []
    for line in open(os.path.join(HERE, "aliases.txt"), encoding="utf-8"):
        line = line.split("#")[0].strip()
        if line:
            out += ["--alias", line]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tot", help="a ttyd-tot checkout (default: fetched to mods/tower-of-trials/tot-src)")
    ap.add_argument("--build", default=os.path.join(ROOT, "build-pc-us-aurora"),
                    help="the US Aurora build (its ttyd_exports.def, when there is one)")
    ap.add_argument("--skip-fields", action="store_true", help="skip mod_fields.py (slow; for header work)")
    a = ap.parse_args()

    src = a.tot or os.path.join(MOD, "tot-src")
    if not a.tot:
        fetch(src)
    rel = os.path.join(src, "ttyd-tools", "rel")
    if not os.path.isdir(os.path.join(rel, "source")):
        sys.exit("no ttyd-tools/rel/source in %s" % src)

    work = os.path.join(MOD, "tot")
    if os.path.isdir(work):
        shutil.rmtree(work)
    shutil.copytree(rel, work, ignore=shutil.ignore_patterns("*.raw", "*.pnproj", "Makefile"))

    py = sys.executable
    run([py, os.path.join(HERE, "pause_extra.py"), "--tot", work])
    if not a.skip_fields:
        run([py, os.path.join(TOOLS, "mod_fields.py"), "--mod", work, "--include", "include",
             "--define", "TTYD_US", "--version", "G8ME01", "--report", os.path.join(MOD, "FIELDS.md"),
             "--apply"] + aliases())
        run([py, os.path.join(HERE, "designators.py"), "--mod", work, "--include", "include",
             "--define", "TTYD_US", "--version", "G8ME01",
             "--report", os.path.join(MOD, "DESIGNATORS.md")] + aliases())

    headers = [py, os.path.join(TOOLS, "mod_headers.py"), "--mod", work,
               "--headers", "include/ttyd/**/*.h", "--headers", "include/gc/*.h",
               "--lst", "include/ttyd.us.lst", "--version", "G8ME01", "--include", "include",
               "--define", "TTYD_US", "--evt-header", "include/evt_cmd.h",
               "--widen-pointer-casts", "--gc-lowmem"] + aliases()
    exports = os.path.join(a.build, "generated", "ttyd_exports.def")
    if os.path.exists(exports):
        headers += ["--exports", exports]
    run(headers)

    gen = os.path.join(work, "generated")
    os.makedirs(gen, exist_ok=True)
    run([py, os.path.join(TOOLS, "mod_asm_stubs.py"), "--mod", work, "--asm", "source/asm/*.s",
         "--ported", os.path.join(HERE, "src", "*.cpp"), "--out", os.path.join(gen, "asm_stubs.cpp")])

    shutil.copy(os.path.join(HERE, "include", "patch.h"), os.path.join(work, "include", "patch.h"))
    os.remove(os.path.join(work, "source", "patch.cpp"))

    run([py, os.path.join(HERE, "manual.py"), "--tot", work])
    run([py, os.path.join(HERE, "byvalue.py"), "--tot", work,
         "--out", os.path.join(work, "generated", "tot_byvalue.h")])

    run([py, os.path.join(HERE, "inventory.py"), "--tot", rel, "--pc", ROOT,
         "--out", os.path.join(MOD, "INVENTORY.md")])
    print("converted: %s" % work)


if __name__ == "__main__":
    main()
