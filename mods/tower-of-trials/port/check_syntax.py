#!/usr/bin/env python3
"""Compile every source of the converted Tower of Trials tree with
-fsyntax-only, with the US Aurora build's flags (as ttyd_add_mod gives a mod),
and count the errors: the porting to-do list, by file and by kind.

  check_syntax.py [--build build-pc-us-aurora] [--jobs N] [--errors FILE]

Errors in Paper Cut's own headers (port/include/...) are counted apart: they
are the same in every file and not the mod's.
"""
import argparse
import collections
import concurrent.futures as cf
import glob
import os
import re
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(MOD))


def flags(build):
    text = open(os.path.join(build, "build.ninja"), encoding="utf-8", errors="replace").read()
    m = re.search(r"^build CMakeFiles/ttyd_dol\.dir/(?:sjis/|statics/)?src/battle/battle_damage\.c\.(?:obj|o):.*\n"
                  r"((?:  .*\n)+)", text, re.M)
    if not m:
        sys.exit("check_syntax: configure %s first" % build)
    out = []
    for ln in m.group(1).splitlines():
        k, _, v = ln.strip().partition(" = ")
        if k in ("DEFINES", "FLAGS", "INCLUDES"):
            out += shlex.split(v, posix=True)
    drop = {"-std=gnu11", "-fgnu89-inline", "-fcommon", "-Werror=implicit-function-declaration", "-w"}
    keep = []
    skip = False
    for i, f in enumerate(out):
        if skip:
            skip = False
            continue
        if f == "-iquote" and i + 1 < len(out) and out[i + 1].replace("\\", "/").endswith("src/battle"):
            skip = True
            continue
        if f in drop or f.startswith(("-g", "-O")):
            continue
        keep.append(f)
    tot = os.path.join(MOD, "tot")
    return keep + ["-std=gnu++20", "-fsyntax-only", "-w", "-ferror-limit=0", "-DTTYD_US=1",
                   "-I" + os.path.join(HERE, "include"), "-I" + os.path.join(tot, "include"),
                   "-include", "ttyd_mod/game_loose.h", "-include", "ttyd_mod/vars.h",
                   "-include", os.path.join(tot, "generated", "tot_namespaces.h"),
                   "-include", os.path.join(tot, "generated", "tot_byvalue.h")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default=os.path.join(ROOT, "build-pc-us-aurora"))
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--errors", default=os.path.join(MOD, "tot", "errors.txt"))
    ap.add_argument("--file", help="compile this one source and print clang's full output (notes included)")
    a = ap.parse_args()
    fl = flags(a.build)
    if a.file:
        r = subprocess.run([os.environ.get("CLANGXX", "clang++"), "-x", "c++", *fl, a.file],
                           capture_output=True, text=True, errors="replace")
        # Paper Cut's own headers' errors first in every file: left out
        out, skip = [], False
        for ln in r.stderr.splitlines():
            if " error: " in ln:
                skip = "/port/include/" in ln.split(" error: ")[0].replace("\\", "/")
            if not skip:
                out.append(ln)
        print("\n".join(out))
        return
    srcs = sorted(glob.glob(os.path.join(MOD, "tot", "source", "*.cpp")) +
                  glob.glob(os.path.join(MOD, "tot", "generated", "*.cpp")) +
                  glob.glob(os.path.join(HERE, "src", "*.cpp")))
    srcs = [s for s in srcs if not re.search(r"[/\\]source[/\\](rel|cxx)\.cpp$", s)]
    clang = os.environ.get("CLANGXX", "clang++")

    def one(src):
        r = subprocess.run([clang, "-x", "c++", *fl, src], capture_output=True, text=True, errors="replace")
        return src, [ln for ln in r.stderr.splitlines() if " error: " in ln]

    per_file = collections.Counter()
    kinds = collections.Counter()
    host = 0
    lines = []
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for src, errs in ex.map(one, srcs):
            for e in errs:
                lines.append(e)
                where = e.split(": error: ")[0].replace("\\", "/")
                if "/port/include/" in where:
                    host += 1
                    continue
                per_file[os.path.relpath(where.rsplit(":", 2)[0], MOD)] += 1
                kinds[re.sub(r"\d+", "N", re.sub(r"'[^']*'", "'X'", e.split(" error: ", 1)[1]))] += 1
    open(a.errors, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("files %d; mod errors %d; in Paper Cut's headers %d" % (len(srcs), sum(per_file.values()), host))
    print("\nby file:")
    for f, n in per_file.most_common(25):
        print("%6d  %s" % (n, f))
    print("\nby kind:")
    for k, n in kinds.most_common(15):
        print("%6d  %s" % (n, k))


if __name__ == "__main__":
    main()
