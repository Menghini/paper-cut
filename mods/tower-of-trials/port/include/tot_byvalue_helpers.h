// Tower of Trials on Paper Cut: a struct argument ToT passes by address (the
// GameCube ABI), as the value the decomp's prototype takes. Used by the
// generated tot_byvalue.h (port/byvalue.py).
//
// ToT keeps colors as uint32_t RGBA words (0x000000FF is opaque black). On
// the big-endian GameCube a pointer to that word was a pointer to a GXColor
// {r, g, b, a}; on the little-endian PC its bytes are the other way round, so
// the word is converted by value, never reinterpreted.
//
// GPL-3.0-or-later (../../LICENSE).

#pragma once

#include <cstdint>
#include <cstring>
#include <type_traits>

namespace tot_port {

template <class T, class P>
inline T ByValue(const P* p) {
    if constexpr (std::is_same_v<T, GXColor> && std::is_integral_v<P> && sizeof(P) == 4) {
        const uint32_t v = static_cast<uint32_t>(*p);
        return GXColor{static_cast<u8>(v >> 24), static_cast<u8>(v >> 16), static_cast<u8>(v >> 8),
                       static_cast<u8>(v)};
    } else {
        static_assert(sizeof(P) == sizeof(T), "a struct argument of another size");
        T out;
        std::memcpy(&out, p, sizeof(T));
        return out;
    }
}

}  // namespace tot_port

namespace tot_port {

// A matrix's 3x4 floats, whichever type holds them: ToT's gc::mtx34 (a
// struct with .m), the decomp's Mtx (the array itself), or a pointer to
// either. ToT writes `x->mtx->m[0][3]`; manual.py makes it TotM(x->mtx)[0][3].
template <class T>
decltype(auto) TotM(T&& m) {
    using U = std::remove_reference_t<T>;
    if constexpr (std::is_array_v<U>) {
        return (m);
    } else if constexpr (std::is_pointer_v<U>) {
        return TotM(*m);
    } else {
        return (m.m);
    }
}

}  // namespace tot_port
