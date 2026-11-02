// Binding to one build of the game.
//
// Every address here is an RVA into CielnosurgeDX.exe, the Steam 2025-07 build
// whose original sha256 starts 04b755ab2eb26f26.  The player's copy is not that
// file -- we rewrite its glyph table and append a .fontex section -- so a digest
// of the whole module would reject the very executable this runs against.  The
// checks below are structural instead.  They are not "stronger" than a digest;
// they test different things, and everything outside these few RVAs is
// unverified.
#pragma once
#include <cstddef>
#include <cstdint>

namespace cielzh {

constexpr uint16_t kMachineAmd64 = 0x8664;
constexpr uint16_t kOptMagicPe32Plus = 0x020B;
constexpr uint32_t kSizeOfImage  = 0x0145C000;  // .fontex only grows it

// Control Flow Guard.  This build has GuardFlags = CF_INSTRUMENTED but does NOT
// set GUARD_CF in DllCharacteristics and ships an empty function table, so the
// process does not enforce CFG and a raw function pointer in a vtable is
// reached by a plain indirect call -- which the disassembly agrees with.
//
// The hooks depend on that.  So these fields are checked, and anything else is
// refused: not because a changed flag would certainly crash -- whether a call
// is rejected also depends on whether the call site checks at all, on the GFID
// metadata, and on the process's effective policy -- but because this
// compatibility argument would no longer have been verified.
constexpr uint16_t kDllCharacteristics = 0x8160;   // no GUARD_CF (0x4000)
constexpr uint16_t kDllCharGuardCf     = 0x4000;
constexpr uint32_t kLoadConfigDirIndex = 10;
constexpr uint32_t kGuardFlags         = 0x0100;   // CF_INSTRUMENTED only
constexpr uint32_t kLoadConfigMinSize  = 0x94;     // must reach GuardFlags

// ac::ACText <- ac::ACSpriteText.  Parsing all 711 complete-object locators in
// the image finds no other class deriving from ACText.
constexpr uint32_t kRvaSpriteTextVtable = 0x00CBB568;  // ac::ACSpriteText
constexpr uint32_t kRvaTextVtable       = 0x00D08B28;  // ac::ACText

constexpr int kSlotSetText = 2;
constexpr int kSlotGetText = 4;

// Vtables hold incremental-link thunks, not the implementations.
constexpr uint32_t kRvaSpriteSetThunk = 0x004016AB;  // -> 0x967F90
constexpr uint32_t kRvaSpriteSetImpl  = 0x00967F90;
constexpr uint32_t kRvaGetThunk       = 0x003F487F;  // -> 0x966D20
constexpr uint32_t kRvaGetImpl        = 0x00966D20;

// ac::ACText is abstract and slot 2 is pure virtual: the thunk goes to MSVC's
// _purecall, which decodes the encoded handler pointer, calls it if one is set
// and otherwise aborts into an int3.  436 pointers in .rdata lead to this same
// thunk -- every pure-virtual slot in the image -- against exactly one for
// ACSpriteText::SetText.
//
// So there is no such thing as "ACText::SetText" to hook, observe or count
// towards UI coverage.  It is verified and left alone: replacing it would turn
// a pure-call abort into a silent success, which is a behaviour change with
// nothing to gain.
constexpr uint32_t kRvaPurecallThunk = 0x0040832F;  // -> 0xA03F8C
constexpr uint32_t kRvaPurecallImpl  = 0x00A03F8C;

// The whole getter, not a prefix: the function is 15 bytes and ends in ret,
// with 0xCC padding after it.
constexpr uint8_t kBodyGet[] = {
    0x48, 0x83, 0x79, 0x20, 0x10,  // cmp qword ptr [rcx+0x20], 0x10
    0x48, 0x8D, 0x41, 0x08,        // lea rax, [rcx+8]
    0x72, 0x03,                    // jb  +3
    0x48, 0x8B, 0x00,              // mov rax, [rax]
    0xC3,                          // ret
};

// The widget system's own readers of its text.
//
// Two stage-one runs -- 900 000 hook calls through the opening, the call and
// touch tutorials, the item tutorial, menus and chat -- found every read of a
// text widget coming from one of these three functions, all ACUIText virtual
// methods: slot 5 (every frame), slot 24 (loading the "text" attribute, which
// reads the old text and writes it back), and slot 0.  No game logic read text
// back in anything those runs reached.
//
// They did not reach everything: the task status and item-category screens were
// not visited, and 104 of the 105 strings kept Japanese in the executable never
// appeared.  So the display layer does not lean on "nobody else reads": a read
// from anywhere outside these ranges is handed the Japanese the game set, not
// the Chinese it displays, and is counted.  These three are the callers that
// get the displayed text, which is what they draw and lay out.
//
// Each is a single RUNTIME_FUNCTION with no chained fragments, so [begin, end)
// covers every call site inside it.  The opening bytes are pinned: the ranges
// are only meaningful for the build they were read from.
struct UiReader {
    uint32_t begin;
    uint32_t end;
    uint8_t prefix[12];
};
constexpr UiReader kUiReaders[] = {
    { 0x009624D0, 0x009625FD,   // ACUIText slot 0
      { 0x48, 0x89, 0x5C, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x10, 0x57, 0x48 } },
    { 0x009627A0, 0x00962BEF,   // ACUIText slot 24, the "text" attribute
      { 0x40, 0x55, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56, 0x41, 0x57 } },
    { 0x00962F60, 0x009636C2,   // ACUIText slot 5, every frame
      { 0x48, 0x8B, 0xC4, 0x55, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56, 0x41, 0x57 } },
};

// A prefix of the setter -- the function is longer, and only its opening is
// pinned here.
constexpr uint8_t kPrefixSpriteSet[] = {
    0x40, 0x53,                    // push rbx
    0x48, 0x83, 0xEC, 0x20,        // sub  rsp, 0x20
    0x80, 0x3A, 0x00,              // cmp  byte ptr [rdx], 0
    0x48, 0x8B, 0xD9,              // mov  rbx, rcx
};

}  // namespace cielzh
