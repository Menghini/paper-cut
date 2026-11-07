#!/usr/bin/env python3
"""The game's file-local functions ToT calls, reached through the pointers
Paper Cut exports for them.

On the GameCube ToT called game functions by address, file-local ones too
(`_get_itemsteal_param`, `get_ptr`...). In the decomp those are `static`, so
the game exports no symbol by their name: it exports a pointer to each,
`port_static__<source path>__<name>` (CMakeLists.txt, ttyd_static_exports).
A mod library that calls them by name would not load. This writes, for each
such function ToT names, a stub under that name that jumps through a pointer
the mod fills from the game's export at start (TotBindStatics, called from
port/src/entry.cpp).

Which source a name is in (`get_ptr` is in five) is found by ToT's GameCube
address: its symbol list against the decomp's config/G8ME01/splits.txt.
Functions of an area's REL ToT names by module and offset are given by hand
(REL_FUNCTIONS below).

The stubs are x86-64 (Windows, Linux): one `jmp` through the pointer, so the
arguments pass through untouched whatever the function's signature.

  statics.py --tot mods/tower-of-trials/tot --out tot/generated/tot_statics.cpp
"""
import argparse
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

# ToT's name -> (the decomp's source, its name there), for functions of an
# area's REL (ToT's list gives them by module, section and offset)
REL_FUNCTIONS = {
    # ToT: module 40 (hei), .text +0x2d8. The decomp's hei_00.c has cam_test
    # (+0x4BC) and cam_test2 (+0x2E4); ToT's names come from the symbol map,
    # and it uses this one to pull the camera back from mini-Hooktail, as the
    # game's opening does with cam_test.
    "evt_hei_00_cam_test": ("rels/hei/src/hei_00.c", "cam_test"),
}


def text_ranges():
    """(start, end, source) of each source's .text in main.dol."""
    out, cur = [], None
    for line in open(os.path.join(ROOT, "config", "G8ME01", "splits.txt"), encoding="utf-8"):
        m = re.match(r"^(\S+\.(?:c|cpp|s)):\s*$", line)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"^\s+\.text\s+start:0x([0-9A-Fa-f]+)\s+end:0x([0-9A-Fa-f]+)", line)
        if m and cur:
            out.append((int(m.group(1), 16), int(m.group(2), 16), cur))
    return out


def ident(path):
    """CMake's MAKE_C_IDENTIFIER of a source path, without the _c."""
    return re.sub(r"_c$", "", re.sub(r"[^A-Za-z0-9_]", "_", path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tot", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    statics = {}  # name -> [sources]
    for line in open(os.path.join(ROOT, "port", "statics_G8ME01.txt"), encoding="utf-8"):
        if line.startswith("#"):
            continue
        parts = line.split()
        for name in parts[1:]:
            statics.setdefault(name, []).append(parts[0])
    ranges = text_ranges()
    kinds, data_ranges = {}, []
    for line in open(os.path.join(ROOT, "config", "G8ME01", "symbols.txt"), encoding="utf-8"):
        m = re.match(r"^(\S+) = \S+ // type:(\w+)", line)
        if m:
            kinds.setdefault(m.group(1), m.group(2))
    cur = None
    for line in open(os.path.join(ROOT, "config", "G8ME01", "splits.txt"), encoding="utf-8"):
        m = re.match(r"^(\S+\.(?:c|cpp|s)):\s*$", line)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"^\s+\.\w+\s+start:0x([0-9A-Fa-f]+)\s+end:0x([0-9A-Fa-f]+)", line)
        if m and cur:
            data_ranges.append((int(m.group(1), 16), int(m.group(2), 16), cur))

    # the functions ToT declares itself in its converted game headers: the
    # prototypes mod_headers.py kept because the decomp declares none (its
    # statics among them), and the variables it binds by name
    used = set()
    for path in glob.glob(os.path.join(a.tot, "include", "**", "*.h"), recursive=True):
        text = open(path, encoding="utf-8").read()
        used |= set(re.findall(r"^[ \t]*(?:extern\s+)?[\w:<>\*&\s]+?\b(\w+)\s*\([^;{}]*\)\s*;", text, re.M))
        used |= set(re.findall(r'ttydGameVar<[^;"]+?>\("(\w+)"\)', text))
        used |= set(re.findall(r"EVT_DECLARE_USER_FUNC\(\s*(\w+)", text))

    # a name some source defines without `static` is exported by that name
    nonstatic = set()
    for src in glob.glob(os.path.join(ROOT, "src", "**", "*.c"), recursive=True) + \
            glob.glob(os.path.join(ROOT, "rels", "**", "*.c"), recursive=True):
        text = open(src, encoding="utf-8", errors="replace").read()
        nonstatic |= {m.group(2) for m in re.finditer(r"^(static\s+)?(?:inline\s+)?[\w\s\*]+?\b(\w+)\s*\([^;{]*\)\s*\{",
                                                       text, re.M) if not m.group(1)}
        nonstatic |= set(re.findall(r"^USER_FUNC\((\w+)\)\s*\{", text, re.M))
        nonstatic |= set(re.findall(r"\bPORT_HOOKABLE\((\w+)\)", text))
    # and a function a game header declares is no file's static
    for h in glob.glob(os.path.join(ROOT, "include", "**", "*.h"), recursive=True):
        nonstatic |= set(re.findall(r"\b(\w+)\s*\([^;{}()]*\)\s*;", open(h, encoding="utf-8", errors="replace").read()))
    found, missing, data = [], [], []
    for line in open(os.path.join(a.tot, "include", "ttyd.us.lst"), encoding="utf-8", errors="replace"):
        line = line.strip()
        m = re.match(r"^([0-9A-Fa-f]{8}):(\w+)$", line)
        if not m or m.group(2) not in used or m.group(2) not in statics or m.group(2) in nonstatic:
            continue
        addr, name = int(m.group(1), 16), m.group(2)
        in_text = any(lo <= addr < hi for lo, hi, _ in ranges)
        if not in_text:
            # file-local data: a ToT header binds it by its plain name
            # (ttydGameVar), which the game doesn't export; by its pointer instead
            src = next((s for lo, hi, s in data_ranges if lo <= addr < hi), None)
            cand = [p for p in statics[name] if src and p.endswith(src)]
            if len(cand) == 1:
                data.append((name, cand[0]))
            else:
                missing.append(name)
            continue
        src = next((s for lo, hi, s in ranges if lo <= addr < hi), None)
        if src is None:
            missing.append(name)
            continue
        cand = [p for p in statics[name] if p.endswith("/" + src) or p == src or p.endswith(src)]
        if len(cand) != 1:
            missing.append(name)
            continue
        found.append((name, cand[0], name))
    for tot_name, (src, dname) in REL_FUNCTIONS.items():
        if tot_name in used:
            found.append((tot_name, src, dname))

    lines = ["// GENERATED by mods/tower-of-trials/port/statics.py: the game's file-local functions",
             "// ToT calls, through the pointers Paper Cut exports for them (port_static__...).",
             '#include "ttyd_mod/ttyd_mod.h"', '#include "ttyd_mod/vars.h"', "",
             "#if !defined(__x86_64__) && !defined(_M_X64)",
             '#error "tot_statics.cpp: the stubs are x86-64 (port/statics.py)"',
             "#endif", "", 'extern "C" {']
    lines += ["void* tot_static_ptr_%s = nullptr;" % n for n, _, _ in found]
    lines += ["}", ""]
    for n, _, _ in found:
        lines.append('__asm__(".text\\n.globl %s\\n.p2align 4\\n%s:\\n    jmp *tot_static_ptr_%s(%%rip)\\n");' % (n, n, n))
    lines += ["", "// The game's functions behind the stubs (from the first frame: the game is up).",
              "void TotBindStatics() {"]
    for n, src, dname in found:
        lines.append('    tot_static_ptr_%s = ttydGameStatic("port_static__%s__%s");' % (n, ident(src), dname))
    lines.append("}")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    # the data: each ToT binding by plain name, by the exported pointer instead
    rebound = 0
    by_name = {}
    for name, src in data:
        by_name.setdefault(name, set()).add(src)
    for path in glob.glob(os.path.join(a.tot, "include", "**", "*.h"), recursive=True):
        text = open(path, encoding="utf-8").read()

        def sub(m):
            srcs = by_name.get(m.group(2))
            if not srcs or len(srcs) != 1:
                return m.group(0)
            return "*static_cast<std::add_pointer_t<%s>>(ttydGameStatic(\"port_static__%s__%s\"))" % (
                m.group(1), ident(next(iter(srcs))), m.group(2))
        new, n = re.subn(r'ttydGameVar<([^;"]+?)>\("(\w+)"\)', sub, text)
        if new != text:
            # (a name in several sources: bound by the address of the use, not here)
            rebound += sum(1 for x in re.findall(r'ttydGameStatic\("port_static__', new)) - \
                sum(1 for x in re.findall(r'ttydGameStatic\("port_static__', text))
            open(path, "w", encoding="utf-8").write(new)
    print("statics.py: %d function stubs; %d data bindings by pointer; not placed: %s"
          % (len(found), rebound, ", ".join(sorted(set(missing))) or "none"))


if __name__ == "__main__":
    main()
