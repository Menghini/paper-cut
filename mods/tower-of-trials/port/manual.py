#!/usr/bin/env python3
"""Hand-ported edits to the converted Tower of Trials tree, as exact text
replacements, so the conversion reruns from a clean checkout
(docs/MODDING.md: "a small script of exact text edits after the tools").

Each edit names its file, the text it expects (once) and its replacement. An
edit whose text isn't found fails loudly: ToT changed, or the tools did, and
the edit needs a look.

  manual.py --tot mods/tower-of-trials/tot
"""
import argparse
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# (file under the converted tree, old text, new text, why)
EDITS = [
    ("source/patches_enemy.cpp",
     "BattleWorkUnit* unit = g_BtlUnit_Entry_trampoline(unit_setup);",
     "BattleWorkUnit* unit = g_BtlUnit_Entry_trampoline(unit_setup);\n"
     "            // PC: ToT's added unit fields (side_fields.py) start at zero,\n"
     "            // as its patched allocation's memset left them\n"
     "            if (unit) TotSideReset_BattleWorkUnit(unit);",
     "a new battle unit's side fields"),
    ("source/patches_enemy.cpp",
     "return g_BtlUnit_Delete_trampoline(unit);",
     "TotSideReset_BattleWorkUnit(unit);\n            return g_BtlUnit_Delete_trampoline(unit);",
     "a deleted battle unit's side fields"),
]


def fixups(tot):
    """Mechanical fixes the tools leave, by pattern rather than exact text."""
    srcs = glob.glob(os.path.join(tot, "source", "*.cpp")) + glob.glob(os.path.join(tot, "include", "**", "*.h"),
                                                                       recursive=True)
    renamed = set()
    for path in srcs:
        renamed |= set(re.findall(r"\bnamespace (\w+)_ns\s*\{", open(path, encoding="utf-8").read()))
    used_ns = set()
    count = 0
    for path in srcs:
        text = open(path, encoding="utf-8").read()
        new = text
        # mod_headers.py renames `namespace ItemType` (named like a game type)
        # to ItemType_ns, but not an alias's target: `= ::ttyd::item_data::ItemType;`
        for name in renamed:
            new = re.sub(r"(namespace\s+\w+\s*=\s*[\w:]*::)%s\s*;" % re.escape(name), r"\g<1>%s_ns;" % name, new)
        used_ns |= set(re.findall(r"\bttyd::(\w+)\b", new))
        if new != text:
            count += 1
            open(path, "w", encoding="utf-8").write(new)
    # ttyd_mod/game_loose.h overloads most game functions (TTYD_LOOSE: an
    # adapter template beside the game's), so `(void*)weaponGetPowerDefault`
    # is ambiguous; ttyd_fn_<name> is the game's own type
    loose = set(re.findall(r"^TTYD_LOOSE\((\w+)\)", open(os.path.join(
        ROOT, "port", "include", "ttyd_mod", "game_loose.h"), encoding="utf-8").read(), re.M))
    cast = re.compile(r"(\(\s*void\s*\*\s*\)\s*|reinterpret_cast<\s*void\s*\*\s*>\s*\(\s*)"
                      r"&?\s*(?:::)?(?:ttyd::\w+::)?(\w+)\b(?!\s*\()")
    for path in srcs:
        text = open(path, encoding="utf-8").read()
        new = cast.sub(lambda m: m.group(1) + "static_cast<ttyd_fn_%s>(&::%s)" % (m.group(2), m.group(2))
                       if m.group(2) in loose else m.group(0), text)
        if new != text:
            open(path, "w", encoding="utf-8").write(new)
    # mod_headers.py binds an extern variable to the game's of that name
    # (ttydGameVar) when the game has one; ToT defines many itself (its own
    # unit_AtomicBoo, ...): those are the mod's, declared plainly again
    defined = set()
    for path in glob.glob(os.path.join(tot, "source", "*.cpp")):
        defined |= set(re.findall(r"^[\w:<>\s\*]*?\b(\w+)\s*(?:\[[^\]]*\])?\s*=\s*\{", open(path, encoding="utf-8").read(), re.M))
    bind = re.compile(r"[ \t]*#define (\w+) ttyd_var_\1\n([ \t]*)extern \"C\+\+\" inline ([^\n]+?)& ttyd_var_\1 = "
                      r"ttydGameVar<[^\n]+>\(\"\1\"\);")
    unbound = 0
    for path in srcs:
        text = open(path, encoding="utf-8").read()
        new = bind.sub(lambda m: "%sextern %s %s;" % (m.group(2), m.group(3), m.group(1))
                       if m.group(1) in defined else m.group(0), text)
        if new != text:
            unbound += len(bind.findall(text)) - len(bind.findall(new))
            open(path, "w", encoding="utf-8").write(new)
    print("manual.py: %d of ToT's own variables unbound from the game's" % unbound)
    # mod_fields.py's casts spell a type as clang printed it, relative to
    # ToT's namespace (ttydAs<battle_database_common::BattleUnitKindPart *>):
    # fully qualified, they mean the same anywhere
    tns = set(used_ns)
    tcast = re.compile(r"\b(ttyd(?:As|Part)<)([^<>]*(?:<[^<>]*>[^<>]*)*)>")

    def qualify(m):
        inner = re.sub(r"(?<![\w:])(%s)::" % "|".join(map(re.escape, sorted(tns, key=len, reverse=True))),
                       r"::ttyd::\1::", m.group(2))
        return m.group(1) + inner + ">"
    for path in srcs:
        text = open(path, encoding="utf-8").read()
        new = tcast.sub(qualify, text) if tns else text
        if new != text:
            open(path, "w", encoding="utf-8").write(new)
    # ToT's gx headers re-declare SDK constants as enumerators (GX_NOP,
    # GX_DRAW_QUADS...) that the PC's GX headers define as macros: the macros
    # (same values) stand, the enumerators go
    macros = set()
    for d in ("extern/aurora/include", "port/include/aurora_overlay", "libs/dolsdk2004/include"):
        for h in glob.glob(os.path.join(ROOT, d, "**", "*.h"), recursive=True):
            macros |= set(re.findall(r"^\s*#\s*define\s+(GX_\w+)\b", open(h, encoding="utf-8", errors="replace").read(), re.M))
    for path in glob.glob(os.path.join(tot, "include", "ttyd", "gx", "*.h")):
        text = open(path, encoding="utf-8").read()
        new = re.sub(r"^[ \t]*(GX_\w+)\s*(?:=[^,\n]*)?,[^\n]*\n",
                     lambda m: "" if m.group(1) in macros else m.group(0), text, flags=re.M)
        if new != text:
            open(path, "w", encoding="utf-8").write(new)
    # ToT's mtx34 is a struct {float m[3][4]}; the decomp's Mtx is the array
    # itself (mod_headers.py aliases one to the other): a Mtx field is
    # indexed directly; which one a name is isn't in the text, so
    # tot_port::TotM (port/include/tot_byvalue_helpers.h) takes either
    for path in glob.glob(os.path.join(tot, "source", "*.cpp")):
        text = open(path, encoding="utf-8").read()
        new = re.sub(r"((?:\b\w+(?:\[[^\]]*\])?(?:->|\.))*\b(?:mtx|matrix))(?:->|\.)m\[", r"tot_port::TotM(\1)[", text)
        if new != text:
            open(path, "w", encoding="utf-8").write(new)
    # a 32-bit word array of ToT's over the decomp's pointer-sized one
    # (unit_work[16] over BattleUnit's EvtWord work[16]/void* workPtr[16]):
    # mod_fields.py's ttydAs<uint32_t[16]> would index 4-byte words in 8-byte
    # slots on the PC; the decomp's own word array is the same 16 words
    # (a pointer ToT keeps in one survives too)
    # and the first-member casts mod_fields.py made for the sound table's
    # nested entries: the member itself
    for path in glob.glob(os.path.join(tot, "source", "*.cpp")):
        text = open(path, encoding="utf-8").read()
        new = re.sub(r"ttydAs<\s*(?:u?int32_t|uint32_t|int32_t)\s*\[\s*16\s*\]\s*>\(([^()]*?(?:->|\.))workPtr\)",
                     r"\1work", text)
        new = re.sub(r"ttydAs<\s*const char\s*\*\s*>\(([\w\.\->\[\]]*?\bentry\[\d\])\)", r"\1.name0", new)
        if new != text:
            open(path, "w", encoding="utf-8").write(new)
    # every ttyd:: namespace the mod names exists, even one whose header
    # mod_headers.py emptied (its declarations are the decomp's now)
    os.makedirs(os.path.join(tot, "generated"), exist_ok=True)
    with open(os.path.join(tot, "generated", "tot_namespaces.h"), "w", encoding="utf-8") as f:
        f.write("// GENERATED by mods/tower-of-trials/port/manual.py: every ttyd:: namespace ToT names.\n#pragma once\n")
        f.write("".join("namespace ttyd::%s {}\n" % n for n in sorted(used_ns)))
    # ToT's own structs (no decomp counterpart) stay in their ttyd:: namespace
    # in the converted headers; mod_fields.py's casts name them unqualified
    # (ttydAs<WinTabBodyInfo[5]>(...)) outside it: bring them to global scope
    game = set()
    for h in glob.glob(os.path.join(ROOT, "include", "**", "*.h"), recursive=True):
        game |= set(re.findall(r"\}\s*(\w+)\s*;|\bstruct\s+(\w+)\s*\{", open(h, encoding="utf-8", errors="replace").read())
                    and [x for t in re.findall(r"\}\s*(\w+)\s*;|\bstruct\s+(\w+)\s*\{",
                                              open(h, encoding="utf-8", errors="replace").read()) for x in t if x])
    lifted = 0
    for h in glob.glob(os.path.join(tot, "include", "ttyd", "**", "*.h"), recursive=True):
        text = open(h, encoding="utf-8").read()
        adds = []
        for ns in re.finditer(r"namespace\s+(ttyd::[\w:]+)\s*\{", text):
            depth, i = 1, ns.end()
            while i < len(text) and depth:
                depth += {"{": 1, "}": -1}.get(text[i], 0)
                i += 1
            for st in re.finditer(r"\bstruct\s+(\w+)\s*\{", text[ns.end():i]):
                if st.group(1) not in game:
                    adds.append("using %s::%s;" % (ns.group(1), st.group(1)))
        if adds:
            text += "\n// ToT's own structs, also by their plain names (manual.py)\n" + "\n".join(sorted(set(adds))) + "\n"
            open(h, "w", encoding="utf-8").write(text)
            lifted += len(set(adds))
    print("manual.py: fixups in %d files; %d namespaces declared; %d structs lifted" % (count, len(used_ns), lifted))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tot", required=True)
    a = ap.parse_args()
    fixups(a.tot)
    bad = 0
    for path, old, new, why in EDITS:
        full = os.path.join(a.tot, path)
        text = open(full, encoding="utf-8").read()
        n = text.count(old)
        if n != 1:
            print("manual.py: %s: expected the text once, found it %d times (%s)" % (path, n, why))
            bad += 1
            continue
        open(full, "w", encoding="utf-8").write(text.replace(old, new))
    print("manual.py: %d edits, %d failed" % (len(EDITS), bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
