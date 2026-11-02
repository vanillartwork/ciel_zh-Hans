// The contract between the loader entry inside the game and this DLL.
//
// Finding a symbol is not the same as agreeing on what it means, so the ABI is
// pinned two ways: the exported names carry a version, and CielZhAbiVersion
// reports one that the loader compares against the number it was built with.
// A loader that finds CielZhAbiVersion missing, or a number it does not know,
// treats the DLL as unusable, logs it, and runs the game's original call.
//
// Rules for changing this file:
//   * Adding an export, or widening behaviour in a way every current caller
//     still reads correctly, bumps kAbiMinor.
//   * Changing a signature, a return-code meaning, or removing an export means
//     a new suffix (…V2) and kAbiMajor.  The old export is not silently
//     repurposed: a stale loader must fail the version check, not call into
//     something that has quietly changed underneath it.
#pragma once
#include <cstdint>

namespace cielzh {
constexpr uint32_t kAbiMajor = 1;
constexpr uint32_t kAbiMinor = 0;
constexpr uint32_t kAbiVersion = (kAbiMajor << 16) | kAbiMinor;
}  // namespace cielzh

extern "C" {

// Returns cielzh::kAbiVersion.  Major in the high 16 bits, minor in the low 16.
__declspec(dllexport) uint32_t __cdecl CielZhAbiVersion(void);

// See entry.h for what the return codes mean.  In particular 5 means something
// of ours is still installed: keep this DLL loaded and do not retry.
__declspec(dllexport) int __cdecl CielZhInitializeV1(char* why, int why_len);
__declspec(dllexport) int __cdecl CielZhDumpTraceV1(const wchar_t* path);
__declspec(dllexport) int __cdecl CielZhShutdownV1(char* why, int why_len);

}  // extern "C"
