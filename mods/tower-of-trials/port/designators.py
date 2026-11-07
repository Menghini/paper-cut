#!/usr/bin/env python3
"""Rename the field designators of a GameCube mod's data tables onto the
decomp's fields, as tools/port/mod_fields.py does for member accesses.

ToT defines its enemies, attacks and maps as C++20 designated initializers:

    BattleWeapon customWeapon_GoombaHeadbonk = {
        .name = nullptr,
        .icon = 0,
        .attribute_flags = AttackTargetClass_Flags::SINGLE_TARGET | ...,

clang's AST keeps no designators for C++ (only the initializer's semantic
form), so mod_fields.py, which works from the AST, leaves these as they were;
the decomp names the same fields otherwise and nothing compiles. This finds
each initializer of a game struct in the text (`Type name[...] = {`), and in
it renames `.field =` by the same mapping mod_fields.py uses: the mod's field
and the decomp's of the same offset and size (an --alias for structs named
otherwise). Run it after mod_fields.py and before mod_headers.py, while the
mod's own struct definitions are still in its headers.

  designators.py --mod DIR [--include include] [--define TTYD_US]
                 [--version G8ME01] [--alias Mod=Decomp ...] [--report FILE]
"""
import argparse
import glob
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "tools", "port"))
import mod_fields  # noqa: E402

DESIGNATOR = re.compile(r"(?<![\w\]\)])\.\s*([A-Za-z_]\w*)\s*=(?!=)")


def separator(text, i):
    """A C++14 digit separator (0x0000'0009), not a character literal."""
    return 0 < i < len(text) - 1 and text[i - 1].isalnum() and text[i + 1].isalnum() and \
        re.search(r"(?:\b0[xXbB])?[0-9A-Fa-f']+$", text[max(0, i - 24):i]) is not None and \
        re.match(r"[0-9]", text[max(0, i - 24):i].split()[-1].lstrip("(-+~[{,=") or "x") is not None


def cast_to(mtyp, dtyp, aliases):
    """The decomp's field type to cast an initializer to, when it isn't the
    mod's (an enum for the mod's int, a struct pointer for its int8_t*), or
    None. C allowed these silently; C++ doesn't."""
    if mod_fields.BITFIELD in (mtyp, dtyp) or "[" in dtyp or "unnamed" in dtyp or "anonymous" in dtyp \
            or dtyp.startswith("<"):
        return None
    def plain(t):
        # without namespaces: ToT's ttyd::battle_database_common::BattleWeapon is the decomp's BattleWeapon
        return re.sub(r"\b(?:\w+::)+", "", mod_fields.canon(t, aliases))
    if plain(mtyp) == plain(dtyp):
        return None
    return re.sub(r"\b(?:struct|union|enum|class)\s+", "", dtyp)


def value_end(text, i, end):
    """Where an initializer's value starting at i ends: the next , or } at
    its own depth."""
    depth = 0
    while i < end:
        c = text[i]
        if c == '"' or (c == "'" and not separator(text, i)):
            q = c
            i += 1
            while i < end and text[i] != q:
                i += 2 if text[i] == "\\" else 1
        elif text.startswith("//", i):
            # a comment inside a value spanning lines (`A |  // why\n B`) is part of it
            j = text.find("\n", i)
            i = j if j >= 0 else end
            continue
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif c == "," and depth == 0:
            return i
        i += 1
    return end


def block_end(text, open_at):
    """The index of the brace closing the one at open_at (strings and
    comments skipped)."""
    depth, i, n = 0, open_at, len(text)
    while i < n:
        c = text[i]
        if c == '"' or (c == "'" and not separator(text, i)):
            q = c
            i += 1
            while i < n and text[i] != q:
                i += 2 if text[i] == "\\" else 1
        elif text.startswith("//", i):
            i = text.find("\n", i)
            if i < 0:
                return n
        elif text.startswith("/*", i):
            i = text.find("*/", i) + 1
            if i <= 0:
                return n
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def rename_in(text, start, end, level, mapping, misses, where):
    """Rename designators at brace depth `level` inside text[start:end];
    returns the new text of that span."""
    out, i, depth, last = [], start, 0, start
    end = min(end, len(text))
    while i < end:
        c = text[i]
        if c == '"' or (c == "'" and not separator(text, i)):
            q = c
            i += 1
            while i < end and text[i] != q:
                i += 2 if text[i] == "\\" else 1
            i += 1
            continue
        if text.startswith("//", i):
            i = text.find("\n", i)
            if i < 0:
                break
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i)
            if j < 0:
                break
            i = j + 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "." and depth == level:
            m = DESIGNATOR.match(text, i)
            if m and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] in "_)]")):
                field = m.group(1)
                hit = mapping(field)
                if hit is None:
                    misses.append((field, where(i)))
                    i = m.end()
                    continue
                new, cast = hit
                if "," in new:
                    # an array the decomp splits into fields: `.f = {a, b, c}`
                    vstart = m.end()
                    while vstart < end and text[vstart].isspace():
                        vstart += 1
                    if vstart < end and text[vstart] == "{":
                        close = block_end(text, vstart)
                        vals = [v.strip() for v in text[vstart + 1:close].split(",") if v.strip()]
                        names = new.split(",")
                        out.append(text[last:m.start()])
                        out.append(", ".join(".%s = %s" % (n, v) for n, v in zip(names, vals)))
                        last = close + 1
                        i = close + 1
                        continue
                    new = new.split(",")[0]
                if new != field:
                    out.append(text[last:m.start(1)])
                    out.append(new)
                    last = m.end(1)
                i = m.end()
                vstart = i
                while vstart < end and text[vstart].isspace():
                    vstart += 1
                if cast and vstart < end and text[vstart] != "{":
                    vend = value_end(text, vstart, end)
                    out.append(text[last:vstart])
                    out.append("(%s)(%s)" % (cast, text[vstart:vend].rstrip()))
                    out.append(text[vstart:vend][len(text[vstart:vend].rstrip()):])
                    last = vend
                    i = vend
                continue
        i += 1
    out.append(text[last:end])
    return "".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mod", required=True)
    ap.add_argument("--include", action="append", default=None)
    ap.add_argument("--define", action="append", default=[])
    ap.add_argument("--sources", default="source/**/*.cpp")
    ap.add_argument("--version", default="G8ME01")
    ap.add_argument("--alias", action="append", default=[])
    ap.add_argument("--report", default=None)
    a = ap.parse_args()
    a.mod = os.path.abspath(a.mod)
    includes = a.include or ["include"]
    aliases = dict(x.split("=", 1) for x in a.alias)
    with tempfile.TemporaryDirectory() as tmp:
        mod_lay, _ = mod_fields.mod_layouts(a.mod, includes, a.define, tmp)
        dec_lay, _ = mod_fields.decomp_layouts(a.version, tmp)
        pc = mod_fields.pc_records(a.version, tmp)
        dec_lay = {k: v for k, v in dec_lay.items() if k in pc}

    types = sorted((t for t in mod_lay if aliases.get(t, t) in dec_lay), key=len, reverse=True)
    decl = re.compile(r"\b(?:const\s+|static\s+|constexpr\s+|inline\s+)*(?:[\w:]+::)?(" +
                      "|".join(map(re.escape, types)) +
                      r")\s+(\*?\s*[A-Za-z_]\w*)\s*(\[[^\]=;{}]*\])?\s*=\s*\{")
    cache = {}
    over = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renames.txt")
    if os.path.exists(over):
        for line in open(over, encoding="utf-8"):
            line = line.split("#")[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                rec, field = k.strip().split(".", 1)
                cache[(rec, field)] = (v.strip(), None)

    def mapper(record):
        dec = aliases.get(record, record)

        def m(field):
            key = (record, field)
            if key not in cache:
                hit = mod_fields.map_field(mod_lay[record], dec_lay[dec], field)
                cache[key] = (hit[0], cast_to(hit[1], hit[2], aliases)) if hit else None
            return cache[key]
        return m

    renamed, misses, tables = 0, [], 0
    for src in sorted(glob.glob(os.path.join(a.mod, a.sources), recursive=True)):
        text = open(src, encoding="utf-8").read()
        pos, parts = 0, []
        for d in decl.finditer(text):
            if d.start() < pos:
                continue
            brace = d.end() - 1
            close = block_end(text, brace)
            level = 2 if d.group(3) else 1
            rel = os.path.relpath(src, a.mod)

            def where(i, t=text, r=rel):
                return "%s:%d" % (r, t.count("\n", 0, i) + 1)
            new = rename_in(text, brace, close + 1, level, mapper(d.group(1)), misses, where)
            renamed += sum(1 for x, y in zip(DESIGNATOR.findall(text[brace:close + 1]), DESIGNATOR.findall(new))
                           if x != y)
            parts.append(text[pos:brace])
            parts.append(new)
            pos = close + 1
            tables += 1
        if parts:
            parts.append(text[pos:])
            open(src, "w", encoding="utf-8").write("".join(parts))

    print("designators: %d tables, %d renamed, %d with no decomp field" % (tables, renamed, len(misses)))
    if a.report:
        by = {}
        for f, w in misses:
            by.setdefault(f, []).append(w)
        lines = ["# Designators with no decomp field of the same offset and size", ""]
        for f, ws in sorted(by.items(), key=lambda kv: -len(kv[1])):
            lines.append("- `.%s` (%d): %s%s" % (f, len(ws), ", ".join(ws[:4]), " ..." if len(ws) > 4 else ""))
        open(a.report, "w", encoding="utf-8").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
