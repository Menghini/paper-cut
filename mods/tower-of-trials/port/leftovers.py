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
    renames = {name: next(iter(t)) for name, t in targets.items()
               if len(t) == 1 and None not in t and next(iter(t)) != name and name not in own
               and len(name) > 4 and not re.match(r"^(unk|pad)_", name)}
    if not renames:
        print("leftovers.py: nothing to rename")
        return
    pat = re.compile(r"(->|\.)(%s)\b(?!\s*\()" % "|".join(map(re.escape, sorted(renames, key=len, reverse=True))))
    count = 0
    for src in glob.glob(os.path.join(a.mod, "source", "*.cpp")):
        text = open(src, encoding="utf-8").read()
        n = [0]

        def sub(m):
            # a designator (`.field =` in a table) is designators.py's
            after = text[m.end():m.end() + 3].lstrip()
            if m.group(1) == "." and after.startswith("=") and not after.startswith("=="):
                return m.group(0)
            n[0] += 1
            return m.group(1) + renames[m.group(2)]
        new = pat.sub(sub, text)
        if new != text:
            open(src, "w", encoding="utf-8").write(new)
            count += n[0]
    print("leftovers.py: %d accesses renamed (%d names known)" % (count, len(renames)))


if __name__ == "__main__":
    main()
