# Tower of Trials for Paper Cut

A port of [Tower of Trials](https://github.com/jdaster64/ttyd-tot) (jdaster64's rogue-like mod for
TTYD, v4.01 r62) to Paper Cut, as a code mod. **Work in progress: it doesn't build yet.**

ToT ships for the GameCube as a replacement `gon.rel` (Hooktail Castle's area module), linked into
the game by a REL loader and patching the game's PowerPC code. Paper Cut runs the decomp natively, so
ToT is converted with Paper Cut's own porting tools (docs/MODDING.md, "Porting a GameCube mod"),
the way the Practice Codes and the TTYD AP mod were.

## Layout

| | |
|---|---|
| `port/port_tot.py` | the whole conversion, rerunnable: fetches ToT at a pinned commit and converts it into `tot/` (not committed) |
| `port/designators.py` | renames the fields in ToT's data tables (`.field = ...`), which `mod_fields.py` doesn't reach |
| `port/manual.py` | fixups by pattern, then the hand-ported edits as exact text |
| `port/include/patch.h` | ToT's `patch.h` for the PC: `hookFunction` through Paper Cut's hook slots; code patches log and are skipped |
| `port/src/entry.cpp` | the library's entry point, in place of the REL's `_prolog` |
| `port/aliases.txt` | ToT's struct names → the decomp's |
| `port/inventory.py` → `INVENTORY.md` | every GameCube patch site in ToT, the game function it lands in, and whether Paper Cut has a hook slot there |
| `port/check_syntax.py` | compiles every converted file `-fsyntax-only`: the porting to-do list |
| `FIELDS.md`, `DESIGNATORS.md` | the field converters' reports: what they couldn't map |
| `CMakeLists.txt` | builds `tot/` as the `tower-of-trials` library (`-DTTYD_LIBRARY_MODS=mods/tower-of-trials`) |

## Running it

```bash
# configure the US Aurora build first (docs/PC_PORT.md); the tools read its flags
python mods/tower-of-trials/port/port_tot.py      # or in parts: --to fields, --from designators --to leftovers, ...
python mods/tower-of-trials/port/check_syntax.py
cmake -S . -B build-pc-us-aurora -DTTYD_LIBRARY_MODS=mods/tower-of-trials
ninja -C build-pc-us-aurora tower-of-trials
```

## Status (2026-11-07)

- **Builds and links** (Linux x86-64, the real US Aurora build's flags, clang 22): all 95 sources compile with
  no errors, and `tower-of-trials.so` links. Of the 805 symbols it takes from the game when loaded, every one is
  a function or variable the game exports by name (checked against the decomp's sources); the only others are the
  C/C++ runtime's and two weak ones it may lack (`_ITM_*`). Not yet built on Windows or loaded into the game.
- The game's file-local functions ToT calls (163) go through stubs bound to the pointers the game exports for
  them (`statics.py`).
- Paper Cut fix on the way: `ttyd_mod/game_loose.h` no longer lists C library functions (`sin`), which made every
  C++ code mod fail to compile on Linux.
- Hooks (`INVENTORY.md`): ToT patches 197 game functions; 109 have a Paper Cut hook slot, 87 need one added to
  `port/mods/hooks.spec` (then `tools/port/gen_hooks.py --apply`). Its 263 `writeBranch*`/`writePatch` sites on code
  are skipped by the port (they log) and each needs redoing as a hook.
- ToT's own area: ToT's REL *is* Hooktail Castle's (`gon`): its maps (`tot_gon_*.cpp`) replace the game's. On the PC
  they are to be registered as the mod's maps; ToT's REL loader (`patches_core.cpp` LoadMap) is replaced by a stub.
- Assets: ToT's maps, text (`msg/US`) and icons come from its patcher, not its repository; they'll be taken from an
  ISO patched with ToT's patcher into this mod's `overlay/`.

What the conversion does beyond Paper Cut's tools, and why, is in each `port/*.py`'s header. Things worth knowing:
ToT's pause-menu fields (`pause_extra.py`) and the fields it adds to battle units (`side_fields.py`) live beside the
game's structs; ToT's RGBA colors are converted by value (`tot_byvalue_helpers.h`), never reinterpreted; ToT's
`wActorThisPtr` is read as the unit id it is.

## Plan

1. **Builds:** clear `check_syntax.py`'s errors (hand edits go in `manual.py`), add the missing hook slots.
2. **Boots:** the library loads, ToT's title screen and its own save file work; assets in `overlay/`.
3. **One run:** the tower's floors, battles and chest rewards (guide pages 2–3, 8).
4. **Everything else:** partners and moves, items and badges, custom enemies, run options and intensity,
   Petalburg hub, journal and achievements, cosmetics (guide pages 4–35).
5. **A mode:** start the tower from Paper Cut's Modes menu.

Each branch-patch site in `INVENTORY.md` becomes a pre/post/replace hook on the function it sits in.

## License

GPL-3.0 (`LICENSE`), as Tower of Trials. This folder only; the rest of Paper Cut is MIT. Tower of Trials is by
jdaster64 and contributors; all credit for its design and content is theirs.
