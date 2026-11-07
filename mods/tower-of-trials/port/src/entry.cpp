// Tower of Trials on Paper Cut: the library's entry point, in place of the
// REL's _prolog (ttyd-tools/rel/source/rel.cpp, left out of the build).
//
// On the GameCube a REL loader linked the mod once the game was set up and
// _prolog ran mod::main(). A library starts before the game's first frame, so
// main() runs from the first frame instead (docs/MODDING.md: "Code that calls
// the game at start belongs in an onFrame callback that runs once"). Global
// constructors already ran when the library loaded.
//
// GPL-3.0-or-later (../../LICENSE).

#include "ttyd_mod/ttyd_mod.h"
#include "ttyd_mod/vars.h"

#include <string_view>

extern "C" const TtydModApi* ttyd_mod_api = nullptr;

namespace mod {
void main();
}

// tot/generated/tot_statics.cpp (port/statics.py): the game's file-local
// functions ToT calls, bound to the pointers the game exports for them
void TotBindStatics();

namespace {

bool g_Started = false;

void StartOnFirstFrame(void*) {
    if (g_Started) {
        return;
    }
    g_Started = true;
    TotBindStatics();
    ttydGameVarsMissing();
    ttyd_mod_api->log("Tower of Trials: starting");
    mod::main();
}

}  // namespace

TTYD_MOD_ENTRY(api) {
    ttyd_mod_api = api;
    if (api->gameId == nullptr || std::string_view(api->gameId) != "G8ME01") {
        api->log("Tower of Trials: the US version (G8ME01) only");
        return 1;
    }
    api->onFrame(StartOnFirstFrame, nullptr);
    return 0;
}
