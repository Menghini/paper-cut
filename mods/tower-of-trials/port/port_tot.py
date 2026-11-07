#!/usr/bin/env python3
"""Convert Tower of Trials (jdaster64/ttyd-tot) into a Paper Cut code mod.

Rerunnable from a clean checkout, as docs/MODDING.md ("Porting a GameCube
mod") describes for the Practice Codes and the TTYD AP mod:

  1. fetch ToT at the pinned commit (or use --tot DIR, a checkout)
  2. copy its mod source (ttyd-tools/rel) to mods/tower-of-trials/tot/
  3. port/pause_extra.py                (ToT's re-laid-out pause menu fields: a struct of its own)
     port/side_fields.py                (fields ToT adds to game structs: beside each object)
     tools/port/mod_fields.py --apply   (struct fields onto the decomp's names)
  4. port/designators.py                (the same, in data tables' .field = ...)
     port/leftovers.py                  (accesses the AST pass didn't reach, by unique name)
  5. tools/port/mod_headers.py          (ToT's game headers become shims)
  6. tools/port/mod_asm_stubs.py        (PowerPC .s routines become stubs)
  7. port/include/patch.h over ToT's    (hooks through Paper Cut's slots)
  8. port/manual.py                     (the hand-ported edits, exact text)
     port/byvalue.py                    (struct-by-address calls onto by-value prototypes)
     port/statics.py                    (the game's file-local functions ToT calls: stubs)
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
    ap.add_argument("--from", dest="from_step", help="start at this step (copy, pause_extra, side_fields, fields, "
                    "designators, leftovers, headers, finish): a run in parts, each resuming the last")
    ap.add_argument("--to", dest="to_step", help="stop after this step")
    a = ap.parse_args()

    src = a.tot or os.path.join(MOD, "tot-src")
    if not a.tot and not a.from_step:
        fetch(src)
    rel = os.path.join(src, "ttyd-tools", "rel")
    if not os.path.isdir(os.path.join(rel, "source")):
        sys.exit("no ttyd-tools/rel/source in %s" % src)

    work = os.path.join(MOD, "tot")
    py = sys.executable
    gen = os.path.join(work, "generated")

    def copy_tree():
        if os.path.isdir(work):
            shutil.rmtree(work)
        shutil.copytree(rel, work, ignore=shutil.ignore_patterns("*.raw", "*.pnproj", "Makefile"))

    def fields():
        run([py, os.path.join(TOOLS, "mod_fields.py"), "--mod", work, "--include", "include",
             "--define", "TTYD_US", "--version", "G8ME01", "--report", os.path.join(MOD, "FIELDS.md"),
             "--apply"] + aliases())

    def designators():
        run([py, os.path.join(HERE, "designators.py"), "--mod", work, "--include", "include",
             "--define", "TTYD_US", "--version", "G8ME01",
             "--report", os.path.join(MOD, "DESIGNATORS.md")] + aliases())

    def leftovers():
        run([py, os.path.join(HERE, "leftovers.py"), "--mod", work, "--include", "include",
             "--define", "TTYD_US", "--version", "G8ME01"] + aliases())

    def headers():
        cmd = [py, os.path.join(TOOLS, "mod_headers.py"), "--mod", work,
               "--headers", "include/ttyd/**/*.h", "--headers", "include/gc/*.h",
               "--lst", "include/ttyd.us.lst", "--version", "G8ME01", "--include", "include",
               "--define", "TTYD_US", "--evt-header", "include/evt_cmd.h",
               "--widen-pointer-casts", "--gc-lowmem"] + aliases()
        exports = os.path.join(a.build, "generated", "ttyd_exports.def")
        if os.path.exists(exports):
            cmd += ["--exports", exports]
        run(cmd)

    def finish():
        os.makedirs(gen, exist_ok=True)
        run([py, os.path.join(TOOLS, "mod_asm_stubs.py"), "--mod", work, "--asm", "source/asm/*.s",
             "--ported", os.path.join(HERE, "src", "*.cpp"), "--out", os.path.join(gen, "asm_stubs.cpp")])
        shutil.copy(os.path.join(HERE, "include", "patch.h"), os.path.join(work, "include", "patch.h"))
        os.remove(os.path.join(work, "source", "patch.cpp"))
        run([py, os.path.join(HERE, "manual.py"), "--tot", work])
        run([py, os.path.join(HERE, "byvalue.py"), "--tot", work,
             "--out", os.path.join(work, "generated", "tot_byvalue.h")])
        run([py, os.path.join(HERE, "statics.py"), "--tot", work,
             "--out", os.path.join(work, "generated", "tot_statics.cpp")])
        run([py, os.path.join(HERE, "inventory.py"), "--tot", rel, "--pc", ROOT,
             "--out", os.path.join(MOD, "INVENTORY.md")])

    steps = [("copy", copy_tree),
             ("pause_extra", lambda: run([py, os.path.join(HERE, "pause_extra.py"), "--tot", work])),
             ("side_fields", lambda: run([py, os.path.join(HERE, "side_fields.py"), "--tot", work])),
             ("fields", fields), ("designators", designators), ("leftovers", leftovers),
             ("headers", headers), ("finish", finish)]
    names = [n for n, _ in steps]
    first = names.index(a.from_step) if a.from_step else 0
    last = names.index(a.to_step) if a.to_step else len(steps) - 1
    for name, fn in steps[first:last + 1]:
        if a.skip_fields and name in ("fields", "designators", "leftovers"):
            continue
        print("== step %s" % name, flush=True)
        fn()
    print("converted: %s" % work)


if __name__ == "__main__":
    main()
