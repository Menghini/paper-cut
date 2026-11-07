#!/usr/bin/env python3
"""Generate port/include/ttyd_mod/game_all.h: every game header (the decomp's
include/) a C++ mod can include, wrapped in ttyd_mod/game_begin.h and
game_end.h (C linkage; the field named delete as delete_).

Each header is compiled alone as C++ with the US Aurora build's flags (from
build-pc-us-aurora/build.ninja); the ones that compile are listed, then the
whole list is compiled together. Also game_loose.h: TTYD_LOOSE (ttyd_mod/
loose.h, C's argument conversions for ported mods) for each function those
headers declare, the game's and the SDK's, that takes arguments and isn't
variadic or a macro. --check: fail if either is stale.
"""
import argparse
import concurrent.futures
import glob
import os
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "port", "include", "ttyd_mod", "game_all.h")
LOOSE = os.path.join(ROOT, "port", "include", "ttyd_mod", "game_loose.h")
# Headers that need another first (they don't include what they use).
NEEDS = {"unit/unit_bomzou.h": "battle/battle_database_common.h",
         "unit/unit_koura.h": "battle/battle_database_common.h"}


def flags():
    text = open(os.path.join(ROOT, "build-pc-us-aurora", "build.ninja"), encoding="utf-8", errors="replace").read()
    # (compiled through a Shift-JIS copy or a statics wrapper: sjis/, statics/)
    m = re.search(r"^build CMakeFiles/ttyd_dol\.dir/(?:sjis/|statics/)?src/battle/battle_damage\.c\.(?:obj|o):.*\n((?:  .*\n)+)", text, re.M)
    if not m:
        sys.exit("gen_game_all: configure build-pc-us-aurora first")
    out = []
    for ln in m.group(1).splitlines():
        k, _, v = ln.strip().partition(" = ")
        if k in ("DEFINES", "FLAGS", "INCLUDES"):
            out += shlex.split(v, posix=True)
    return [f for f in out if f not in ("-std=gnu11", "-fgnu89-inline", "-Xclang", "-gcodeview")
            and not f.startswith(("-g", "-O", "--dependent-lib", "-Werror"))]


def compiles(fl, tmp, name, body):
    p = os.path.join(tmp, re.sub(r"\W", "_", name) + ".cpp")
    with open(p, "w") as f:
        f.write(body)
    r = subprocess.run([os.environ.get("CLANGXX", "clang++"), "-x", "c++", "-std=gnu++20", "-fsyntax-only", "-w", *fl, p],
                       cwd=ROOT, capture_output=True, text=True, errors="replace")
    return r.returncode == 0, r.stderr


LOC = re.compile(r"<([A-Za-z]:[^:<>]+|/[^:<>]+):\d+:\d+")
FUNC = re.compile(r"^[|` ]*[|`]-FunctionDecl 0x[0-9a-f]+ (?:prev 0x[0-9a-f]+ )?<(\S+?)[,>].*? (?:implicit )?(?:used )?(?:referenced )?(\w+) '([^']*)'")

EVT_FUNC = re.compile(r"^(?:s32|int) \((?:struct )?EventEntry \*, (?:BOOL|int)\)")


def loose_functions(fl, tmp, text):
    """The functions game_all.h declares from the game's or the SDK's headers
    that a loose overload suits."""
    p = os.path.join(tmp, "loose.cpp")
    with open(p, "w") as f:
        f.write(text)
    cxx = os.environ.get("CLANGXX", "clang++")
    base = [cxx, "-x", "c++", "-std=gnu++20", "-w", *fl, p]
    ast = subprocess.run(base[:1] + ["-fsyntax-only", "-Xclang", "-ast-dump", "-fno-color-diagnostics"] + base[1:],
                         cwd=ROOT, capture_output=True, text=True, errors="replace").stdout
    macros = set(re.findall(r"^#define (\w+)", subprocess.run(base[:1] + ["-E", "-dM"] + base[1:], cwd=ROOT,
                            capture_output=True, text=True, errors="replace").stdout, re.M))
    # (and the port's overlay of the SDK's headers: portGXSetBlendMode for GXSetBlendMode)
    roots = tuple(os.path.normcase(os.path.join(ROOT, d)) for d in ("include", os.path.join("extern", "aurora", "include"),
                                                                    os.path.join("port", "include", "aurora_overlay")))
    # the C library's own functions (sin...), which a game header may declare
    # again: C++'s <cmath> overloads them (float, long double), so a loose
    # overload's decltype(&sin) is ambiguous with libstdc++ and libc++, and a
    # C++ mod calls them through <cmath> anyway
    libc = set(re.findall(r"\b(\w+)\s*\(", open(os.path.join(ROOT, "include", "libc_decls.h"),
                                                    encoding="utf-8").read()))
    # clang prints a location's file only when it changes (in print order)
    cur, names = "", set()
    for ln in ast.splitlines():
        m = FUNC.match(ln)
        if m:
            first = LOC.match("<" + m.group(1))
            if first:
                cur = first.group(1)
            name, typ = m.group(2), m.group(3)
            where = os.path.normcase(os.path.abspath(os.path.join(ROOT, cur)))
            # not a script's user function: a script takes its address (one
            # overload, no template beside it), and nothing calls one
            if (where.startswith(roots) and name not in macros and name not in libc and not EVT_FUNC.match(typ)
                    and "..." not in typ and not typ.endswith(("()", "(void)"))):
                names.add(name)
        for loc in LOC.finditer(ln):
            cur = loc.group(1)
    return sorted(names)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    fl = flags()
    headers = sorted(os.path.relpath(p, os.path.join(ROOT, "include")).replace(os.sep, "/")
                     for p in glob.glob(os.path.join(ROOT, "include", "**", "*.h"), recursive=True))
    with tempfile.TemporaryDirectory() as tmp:
        def one(h):
            pre = f'#include "{NEEDS[h]}"\n' if h in NEEDS else ""
            ok, _ = compiles(fl, tmp, h, f'#include "ttyd_mod/game_begin.h"\n{pre}#include "{h}"\n'
                                         f'#include "ttyd_mod/game_end.h"\n')
            return h, ok
        with concurrent.futures.ThreadPoolExecutor(12) as ex:
            ok = [h for h, good in ex.map(one, headers) if good]
        lines = ["/* GENERATED by tools/port/gen_game_all.py. Do not edit.",
                 " * Every game header (the decomp's include/) that compiles as C++, for a C++",
                 " * mod that wants the whole game API in one include. */",
                 "#ifndef TTYD_MOD_GAME_ALL_H", "#define TTYD_MOD_GAME_ALL_H", '#include "ttyd_mod/game_begin.h"']
        lines += sorted({f'#include "{NEEDS[h]}"' for h in ok if h in NEEDS})
        lines += [f'#include "{h}"' for h in ok]
        lines += ['#include "ttyd_mod/game_end.h"', "#endif", ""]
        text = "\n".join(lines)
        good, err = compiles(fl, tmp, "all", text + '#include "ttyd_mod/ttyd_mod.h"\n')
        if not good:
            sys.exit("gen_game_all: the headers don't compile together:\n" + err[-3000:])
        names = loose_functions(fl, tmp, text)
        # the decomp's script macros (END, RETURN, IF_EQUAL...): the game's
        # headers need them, a ported mod has its own (ttyd-tools' evt_cmd.h)
        # and identifiers they'd clobber (an enum's END)
        script = sorted(set(re.findall(r"^#define (\w+)", open(os.path.join(ROOT, "include", "evt", "evt_cmd.h"),
                                                                 encoding="utf-8").read(), re.M)))
        body = (["#ifdef __cplusplus"] + [f"TTYD_LOOSE({n})" for n in names] + ["#endif"]
                + [f"#undef {n}" for n in script])
        loose = "\n".join(["/* GENERATED by tools/port/gen_game_all.py. Do not edit.",
                           " * C's argument conversions on the game's functions, for ported GameCube",
                           " * mods (ttyd_mod/loose.h). */",
                           "#ifndef TTYD_MOD_GAME_LOOSE_H", "#define TTYD_MOD_GAME_LOOSE_H",
                           '#include "ttyd_mod/game_all.h"', '#include "ttyd_mod/loose.h"']
                          + body + ["#endif", ""])
        good, err = compiles(fl, tmp, "loose", text + '#include "ttyd_mod/loose.h"\n' + "\n".join(body) + "\n")
        if not good:
            sys.exit("gen_game_all: game_loose.h doesn't compile:\n" + err[-3000:])
    stale = 0
    for path, out, what in ((OUT, text, f"{len(ok)} of {len(headers)} headers"),
                            (LOOSE, loose, f"{len(names)} functions")):
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if a.check:
            print(f"{'ok   ' if old == out else 'STALE'} {os.path.relpath(path, ROOT)} ({what})")
            stale += old != out
        elif old != out:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(out)
            print(f"wrote {os.path.relpath(path, ROOT)} ({what})")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
