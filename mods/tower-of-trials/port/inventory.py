#!/usr/bin/env python3
"""Inventory of Tower of Trials' GameCube code patches, mapped onto Paper Cut.

For every patch site in ToT's source (hookFunction, writeBranch*, writePatch,
hookInstruction), find the game function it lands in (ToT's symbol list gives
the address, the decomp's config/G8ME01/symbols.txt gives the function that
holds it) and whether Paper Cut has a hook slot on that function.

  inventory.py --tot TOT/ttyd-tools/rel --pc PAPER_CUT --out PORTING_INVENTORY.md
"""
import argparse
import bisect
import collections
import os
import re

CALL = re.compile(r"\b(?:mod::|patch::)?(hookFunction|hookInstruction|writeBranchPair|writeBranchBL|writeBranchMain|writeBranch|writePatch)\s*\(")
SYM = re.compile(r"^(\S+) = (\.\w+):0x([0-9A-Fa-f]+); // type:(\w+)(?: size:0x([0-9A-Fa-f]+))?")


def load_lst(path):
    """ToT's symbol list: name -> GameCube address (DOL symbols only)."""
    out = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        m = re.match(r"^([0-9A-Fa-f]{8}):(\S+)", line)
        if m:
            out[m.group(2)] = int(m.group(1), 16)
    return out


def load_symbols(path):
    """The decomp's functions: sorted (start, end, name)."""
    funcs = []
    for line in open(path, encoding="utf-8"):
        m = SYM.match(line)
        if m and m.group(4) == "function":
            start = int(m.group(3), 16)
            size = int(m.group(5) or "4", 16)
            funcs.append((start, start + size, m.group(1)))
    funcs.sort()
    return funcs


def containing(funcs, starts, addr):
    i = bisect.bisect_right(starts, addr) - 1
    if i >= 0 and funcs[i][0] <= addr < funcs[i][1]:
        return funcs[i][2]
    return None


def first_arg(text, pos):
    """The call's first argument, as written."""
    depth, i, start = 0, pos, pos
    while i < len(text):
        c = text[i]
        if c in "([{<":
            depth += 1
        elif c in ")]}>":
            if depth == 0:
                break
            depth -= 1
        elif c == "," and depth == 0:
            break
        i += 1
    return " ".join(text[start:i].split())


def target_name(arg):
    """The symbol a first argument names: ns::Func, or g_Name inside a cast."""
    arg = re.sub(r"reinterpret_cast<[^>]*>\s*\(", "(", arg)
    arg = arg.strip("() &")
    m = re.search(r"0x([0-9A-Fa-f]{8})U?", arg)
    if m:
        return None, int(m.group(1), 16)
    name = arg.split("::")[-1].strip("() &")
    return name, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tot", required=True)
    ap.add_argument("--pc", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    lst = load_lst(os.path.join(a.tot, "include", "ttyd.us.lst"))
    # ToT's patch sites: `extern const int32_t g_Name = 0x8012....;` (US block of patch_globals.cpp)
    pg = open(os.path.join(a.tot, "source", "patch_globals.cpp"), encoding="utf-8").read()
    us = pg
    m = re.search(r"#ifdef TTYD_US(.*?)#elif", pg, re.S)
    if m:
        us = m.group(1)
    for g in re.finditer(r"\b(g_\w+)\s*=\s*0x([0-9A-Fa-f]{8})", us):
        lst.setdefault(g.group(1), int(g.group(2), 16))
    funcs = load_symbols(os.path.join(a.pc, "config", "G8ME01", "symbols.txt"))
    starts = [f[0] for f in funcs]
    slots = set()
    for line in open(os.path.join(a.pc, "port", "mods", "hook_slots.txt"), encoding="utf-8"):
        p = line.split()
        if len(p) >= 2 and p[0].isdigit():
            slots.add(p[1])
    picked = set()
    spec = os.path.join(a.pc, "port", "mods", "hooks.spec")
    for line in open(spec, encoding="utf-8"):
        s = line.split("#")[0].strip()
        if s and not s.startswith("@") and not s.startswith("-"):
            picked.add(s)

    rows = []
    src = os.path.join(a.tot, "source")
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".cpp") or fn in ("patch.cpp", "patch_globals.cpp"):
            continue
        text = open(os.path.join(src, fn), encoding="utf-8", errors="replace").read()
        for m in CALL.finditer(text):
            kind = m.group(1)
            line = text.count("\n", 0, m.start()) + 1
            arg = first_arg(text, m.end())
            name, addr = target_name(arg)
            if addr is None and name is not None:
                addr = lst.get(name)
            func = containing(funcs, starts, addr) if addr is not None else None
            if func is None and name and kind == "hookFunction":
                func = name
            rows.append((fn, line, kind, name or ("0x%08X" % addr if addr else arg), addr, func))

    by_func = collections.OrderedDict()
    for r in rows:
        by_func.setdefault(r[5] or "(unresolved)", []).append(r)

    kinds = collections.Counter(r[2] for r in rows)
    have = [f for f in by_func if f in slots]
    need = [f for f in by_func if f not in slots and f != "(unresolved)"]

    L = []
    L.append("# Tower of Trials → Paper Cut: patch inventory")
    L.append("")
    L.append("Generated by `inventory.py` from ToT's source and Paper Cut's hook slots. "
             "Each GameCube patch site is resolved to the game function that holds it "
             "(ToT's `ttyd.us.lst` address → the decomp's `config/G8ME01/symbols.txt`).")
    L.append("")
    L.append("| | Count |")
    L.append("|---|---|")
    for k, v in kinds.most_common():
        L.append("| `%s` calls | %d |" % (k, v))
    L.append("| Game functions touched | %d |" % (len(by_func) - (1 if "(unresolved)" in by_func else 0)))
    L.append("| ...with a Paper Cut hook slot today | %d |" % len(have))
    L.append("| ...needing a new slot (`port/mods/hooks.spec`) | %d |" % len(need))
    L.append("| Sites not resolved to a function | %d |" % len(by_func.get("(unresolved)", [])))
    L.append("")
    L.append("`hookFunction` on a function with a slot ports as `TTYD_HOOK_FUNCTION` (ttyd_mod/compat.h). "
             "Every `writeBranch*` / `writePatch` on code is skipped by the port and must be redone as a "
             "pre/post/replace hook on the function it sits in; the function column says which.")
    L.append("")
    for title, keys in (("Needs a new hook slot", need), ("Has a hook slot", have),
                        ("Unresolved", ["(unresolved)"] if "(unresolved)" in by_func else [])):
        L.append("## %s (%d)" % (title, len(keys)))
        L.append("")
        L.append("| Game function | Sites (kind: ToT file:line, symbol) |")
        L.append("|---|---|")
        for f in sorted(keys):
            sites = "<br>".join("%s: %s:%d `%s`" % (r[2], r[0], r[1], r[3]) for r in by_func[f])
            L.append("| `%s`%s | %s |" % (f, " (hand-picked)" if f in picked else "", sites))
        L.append("")
    open(a.out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("sites %d, functions %d, with slot %d, need slot %d, unresolved %d" % (
        len(rows), len(by_func), len(have), len(need), len(by_func.get("(unresolved)", []))))


if __name__ == "__main__":
    main()
