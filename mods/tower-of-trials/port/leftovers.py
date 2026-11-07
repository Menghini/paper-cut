#!/usr/bin/env python3
"""Rename the game-struct field accesses mod_fields.py left in the text.

mod_fields.py renames the accesses clang's AST shows it; some it doesn't
reach (inside lambdas handed to a macro, in code a template only parses).
This renames what is left, by text: `->name` / `.name` for each field of a
game struct whose name no other struct of the mod uses (ToT's own classes
included) and that maps onto the decomp's by offset and size, as
mod_fields.py maps it. Runs after mod_fields.py and designators.py, while
ToT's own struct definitions are still in its headers.

  leftovers.py --mod DIR [--include include] [--define TTYD_US] [--alias M=D ...]
"""
import argparse
import collections
import glob
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "tools", "port"))
import mod_fields  # noqa: E402

# ToT's sub-structs inside game structs that the decomp lays out as the
# game struct's own fields (BattleWorkUnit.movement_params.move_frames is
# BattleUnit.moveFrames): renamed by offset and size, at any depth
SUBSTRUCTS = {"movement_params", "ac_manager_work", "act_record_work"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", required=True)
    ap.add_argument("--include", action="append", default=None)
    ap.add_argument("--define", action="append", default=[])
    ap.add_argument("--version", default="G8ME01")
    ap.add_argument("--alias", action="append", default=[])
    a = ap.parse_args()
    a.mod = os.path.abspath(a.mod)
    includes = a.include or ["include"]
    aliases = dict(x.split("=", 1) for x in a.alias)
    with tempfile.TemporaryDirectory() as tmp:
        mod_lay, _ = mod_fields.mod_layouts(a.mod, includes, a.define, tmp)
        dec_lay, _ = mod_fields.decomp_layouts(a.version, tmp)
        pc = mod_fields.pc_records(a.version, tmp)
        dec_lay = {k: v for k, v in dec_lay.items() if k in pc}

    # every field name the mod's own headers declare outside the game's structs
    own = set()
    # ...and inside the sources' own structs and classes
    for src in glob.glob(os.path.join(a.mod, "source", "*.cpp")):
        text = open(src, encoding="utf-8").read()
        for body in re.findall(r"\b(?:struct|class|union)\s+\w+\s*(?::[^{;]*)?\{(.*?)\n\};", text, re.S):
            own |= set(re.findall(r"^\s+[\w:<>\*\s]+?\b(\w+)\s*(?:\[[^\]]*\])?\s*(?:=[^;]*)?;", body, re.M))
    for h in glob.glob(os.path.join(a.mod, "include", "*.h")):
        own |= set(re.findall(r"^\s+[\w:<>\*\s]+?\b(\w+)\s*(?:\[[^\]]*\])?\s*(?:=[^;]*)?;", open(h, encoding="utf-8").read(),
                              re.M))
    targets = collections.defaultdict(set)
    for rec, lay in mod_lay.items():
        dec = aliases.get(rec, rec)
        for path, _, _, _ in mod_fields.flatten(lay):
            if "." in path:
                continue
            hit = mod_fields.map_field(lay, dec_lay[dec], path) if dec in dec_lay else None
            targets[path].add(hit[0] if hit else None)
    # a name the decomp also uses for a field (count, timer...) may be one
    # of its structs' already, reached through another path: left alone
    decomp_names = set()
    for lay in dec_lay.values():
        decomp_names |= {p.split(".")[-1].split("[")[0] for p, _, _, _ in mod_fields.flatten(lay)}
    renames = {name: next(iter(t)) for name, t in targets.items()
               if len(t) == 1 and None not in t and next(iter(t)) != name and name not in own
               and name not in decomp_names and len(name) >= 8 and not re.match(r"^(unk|pad)_", name)
               and "." not in next(iter(t))}
    # x->movement_params.move_frames: ToT's sub-struct, the decomp's own
    # fields at the same offsets (moveFrames): by offset and size, one level
    nested = {}
    for rec, lay in sorted(mod_lay.items(), key=lambda kv: kv[0] != "BattleWorkUnit"):
        dec = aliases.get(rec, rec)
        if dec not in dec_lay:
            continue
        dflat = mod_fields.flatten(dec_lay[dec])
        for path, off, size, typ in mod_fields.flatten(lay):
            outer = path.split(".")[0]
            if "." not in path or outer not in SUBSTRUCTS:
                continue
            same = [p for p, o, sz, _ in dflat if o == off and sz == size]
            if not same:
                # a size that counts the padding after the field: the same type there
                same = [p for p, o, _, t in dflat if o == off and
                        mod_fields.canon(t, aliases) == mod_fields.canon(typ, aliases)]
            inner = path.split(".", 1)[1]
            # the first struct's mapping wins (BattleWorkUnit before its parts)
            if same and inner not in nested.get(outer, {}):
                nested.setdefault(outer, {})[inner] = min(same, key=lambda p: p.count("."))
    # hand renames (renames.txt, also designators.py's): plain names only
    over = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renames.txt")
    for line in open(over, encoding="utf-8") if os.path.exists(over) else []:
        line = line.split("#")[0].strip()
        if "=" in line and "," not in line:
            k, v = line.split("=", 1)
            renames[k.split(".", 1)[1].strip()] = v.strip()
    if not renames and not nested:
        print("leftovers.py: nothing to rename")
        return
    pat = re.compile(r"(->|\.)(%s)\b(?!\s*\()" % "|".join(map(re.escape, sorted(renames, key=len, reverse=True))))
    count = 0
    for src in glob.glob(os.path.join(a.mod, "source", "*.cpp")):
        text = open(src, encoding="utf-8").read()
        n = [0]

        def sub(m):
            # a designator (`.field =` in a table) is designators.py's
            # (`{ .field = ...` or `, .field = ...`: after a brace or comma, not
            # after an object, as in `snd_table.field = ...`)
            after = text[m.end():m.end() + 3].lstrip()
            before = text[:m.start()].rstrip()[-1:]
            if m.group(1) == "." and after.startswith("=") and not after.startswith("==") and before in ("{", ","):
                return m.group(0)
            n[0] += 1
            return m.group(1) + renames[m.group(2)]
        new = pat.sub(sub, text)
        if new != text:
            open(src, "w", encoding="utf-8").write(new)
            count += n[0]
    ncount = 0
    for src in glob.glob(os.path.join(a.mod, "source", "*.cpp")):
        text = open(src, encoding="utf-8").read()
        new = text
        for outer, inner in nested.items():
            # the longest inner path first (movement_params.sounds.walk_sound_left)
            new = re.sub(r"(->|\.)%s\.(\w+(?:\.\w+)*)\b" % re.escape(outer),
                         lambda m: next((m.group(1) + inner[k] + m.group(2)[len(k):]
                                         for k in sorted(inner, key=len, reverse=True)
                                         if m.group(2) == k or m.group(2).startswith(k + ".")), m.group(0)), new)
        if new != text:
            ncount += 1
            open(src, "w", encoding="utf-8").write(new)
    print("leftovers.py: %d accesses renamed (%d names known); sub-structs %s in %d files"
          % (count, len(renames), ", ".join(sorted(nested)) or "none", ncount))


if __name__ == "__main__":
    main()
