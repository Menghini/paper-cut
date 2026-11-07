# Tower of Trials as a Paper Cut code mod (docs/MODDING.md, "Porting a
# GameCube mod"). Added by the game's build with
#   cmake ... -DTTYD_LIBRARY_MODS=mods/tower-of-trials
# after port/port_tot.py has made the converted tree, tot/.
#
# GPL-3.0-or-later, as Tower of Trials (LICENSE).

set(_tot ${CMAKE_CURRENT_SOURCE_DIR}/tot)
if(NOT EXISTS ${_tot}/source)
    message(WARNING "tower-of-trials: no converted tree; run "
        "python mods/tower-of-trials/port/port_tot.py, then configure again")
    return()
endif()

file(GLOB _tot_srcs CONFIGURE_DEPENDS
    ${_tot}/source/*.cpp
    ${_tot}/generated/*.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/port/src/*.cpp)
# GameCube-only: the REL's runtime (prolog/epilog, C++ runtime for a REL);
# the library has its own (port/src/entry.cpp is the entry point)
list(FILTER _tot_srcs EXCLUDE REGEX "/source/(rel|cxx)\\.cpp$")

ttyd_add_mod(tower-of-trials ${_tot_srcs})
target_include_directories(tower-of-trials PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/port/include   # patch.h first
    ${_tot}/include)
target_compile_definitions(tower-of-trials PRIVATE TTYD_US=1)
target_compile_features(tower-of-trials PRIVATE cxx_std_20)
target_compile_options(tower-of-trials PRIVATE
    "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-include ttyd_mod/game_loose.h>"
    "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-include ttyd_mod/vars.h>"
    "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-include ${_tot}/generated/tot_namespaces.h>")
