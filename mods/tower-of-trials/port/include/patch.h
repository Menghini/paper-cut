// Tower of Trials' patch.h for Paper Cut (replaces ttyd-tools/rel/include/patch.h
// in the converted tree; docs/MODDING.md, "Porting a GameCube mod").
//
// On the GameCube these functions rewrote the game's PowerPC instructions. The
// PC build runs native code, so:
//   - hookFunction(fn, dest) replaces the game's function through its hook
//     slot (ttyd_mod/compat.h) and returns the game's own function, as the
//     GameCube trampoline did. A function without a slot stays as the game has
//     it and the log says so (port/mods/hooks.spec to add one).
//   - writeBranch*, writeBranchPair and writePatch on game code do nothing and
//     log once per call site: each is ported by hand as a hook (see
//     mods/tower-of-trials/INVENTORY.md for the function each one sits in).
//   - writePatch on data the mod owns, or on the PC game's own data (a pointer
//     the PC build gave it, not a GameCube address), is still a memcpy.
//
// Copyright (C) jdaster64 and contributors; Paper Cut port changes likewise
// GPL-3.0-or-later (see ../../LICENSE).

#pragma once

#include "ttyd_mod/compat.h"

#include <cstdint>
#include <cstring>
#include <type_traits>

namespace mod {

namespace port_detail {

// A GameCube address the mod kept as a number (patch_globals.cpp's
// `g_..._BH = 0x8012...`): code or data the PC build has elsewhere.
inline bool IsGameCubeAddress(const void* p) {
    const uintptr_t a = reinterpret_cast<uintptr_t>(p);
    return a >= 0x80000000u && a < 0x81800000u;
}

inline void Skipped(const char* what, const void* p) {
    ttyd_mod_api->log("ToT port: skipped %s at %p (GameCube code; needs a hand port)", what, p);
}

}  // namespace port_detail

inline void clear_DC_IC_Cache(void*, uint32_t) {}

inline void writeBranch(void* ptr, void*) { port_detail::Skipped("writeBranch", ptr); }
inline void writeBranchBL(void* ptr, void*) { port_detail::Skipped("writeBranchBL", ptr); }
inline void writeBranchMain(void* ptr, void*, uint32_t) { port_detail::Skipped("writeBranchMain", ptr); }
inline void writeStandardBranches(void* address, void (*)(), void (*)()) {
    port_detail::Skipped("writeStandardBranches", address);
}

inline void writePatch(void* destination, const void* patch_start, uint32_t patch_len) {
    if (destination == nullptr || port_detail::IsGameCubeAddress(destination)) {
        port_detail::Skipped("writePatch", destination);
        return;
    }
    std::memcpy(destination, patch_start, patch_len);
}

inline void writePatch(void* destination, const void* patch_start, const void* patch_end) {
    writePatch(destination, patch_start,
               static_cast<uint32_t>(reinterpret_cast<uintptr_t>(patch_end) -
                                     reinterpret_cast<uintptr_t>(patch_start)));
}

inline void writePatch(void* destination, uint32_t patch_data) {
    writePatch(destination, &patch_data, sizeof(uint32_t));
}

inline void writeBranchPair(void* original_start, void*, void*, void*) {
    port_detail::Skipped("writeBranchPair", original_start);
}
inline void writeBranchPair(void* original_start, void*, void*) {
    port_detail::Skipped("writeBranchPair", original_start);
}

// hookFunction(fn, dest): by the function's name, through its hook slot. A
// macro so the name is known (a template only sees an address, and on Windows
// a library's address of a game function is an import thunk).
// ToT's hook lambdas take its own types (bool for the game's BOOL, its own
// struct names), as ttyd-tools' hookFunction allowed: the replacement goes in
// as its own function pointer (a captureless lambda's, +dest), and the game's
// function comes back as whatever pointer the trampoline variable is
// (ttyd_mod/compat.h's TtydOriginal). Only the game function's name is used:
// Paper Cut's hook slots are found by name, and the function itself may be
// overloaded (ttyd_mod/game_loose.h's adapters), so its type isn't deduced.
template <typename Dest>
TtydOriginal hookFunctionNamed(const char* name, Dest destination) {
    if constexpr (std::is_pointer_v<Dest>) {
        return ttydHookFunction(name, destination);
    } else {
        return ttydHookFunction(name, +destination);
    }
}

}  // namespace mod

#define hookFunction(fn, ...) hookFunctionNamed(#fn, __VA_ARGS__)
