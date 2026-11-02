// The display layer: Chinese on screen, Japanese everywhere else.
//
// The game uses some strings both as text it shows and as keys it looks things
// up by.  Translating such a string where the game keeps it broke the lookup --
// that was the crash when Ion was called over.  So nothing the game stores is
// changed.  What changes is the copy a text widget is handed at the moment it is
// told what to show, and only for strings in a table built from our own
// translations.
//
// Three rules make that safe rather than merely likely to be safe:
//
//   * Replacement happens only on the way into ac::ACSpriteText::SetText.  The
//     table is matched against the whole text, or against a name inside a
//     <CLY2>...  span (a nameplate, or a name in the message log) -- never
//     against arbitrary substrings.
//
//   * Every replacement is remembered per widget, with the Japanese the game
//     set.  A read of that widget from anywhere other than the widget system's
//     own three methods (version.h, kUiReaders) gets the Japanese back.  So
//     game code that reads a widget's text to compare it with a key sees what it
//     wrote, whether or not anybody has observed such a read.  Each one is
//     counted and its call site kept, because it would be the first evidence of
//     a read the stage-one runs did not reach.
//
//   * If a replacement cannot be remembered -- the table of widgets is full --
//     it is not made.  The text stays Japanese and that is counted too.
//
// The table holds no Japanese: only a 64-bit FNV-1a hash and the length of each
// Japanese string, and our Chinese.  It is generated on the player's machine
// from the player's own game data (tools/build_text_table.py), which uses the
// same hash.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>

namespace cielzh {

// FNV-1a, 64-bit, over the UTF-8 bytes.  tools/build_text_table.py must agree;
// both sides check the same known answers.
uint64_t TextHash(const char* p, size_t n);

constexpr uint32_t kMatchWhole = 1;   // the widget's whole text is this string
constexpr uint32_t kMatchName  = 2;   // also as the name in a <CLY2>... span

extern const wchar_t kTextTableName[];   // beside the executable

// The executable's base, for telling the widget system's own readers from
// everybody else.  Set before the hooks are armed.
void DisplayInit(const void* module_base);

// 0 when the table is loaded and replacement is on.  Anything else leaves it
// off, with the reason in `why` and in the dump header -- the hooks keep
// recording either way.
int DisplayLoad(const wchar_t* path, char* why, size_t why_len);
int DisplayLoadBytes(const uint8_t* data, size_t n, char* why, size_t why_len);

// What to hand the game's setter: `text` itself, or a Chinese copy that stays
// valid until the setter returns (`scratch` or the table's own storage).
const char* DisplayOnSet(void* self, const char* text, std::string& scratch);

// What to hand a reader: `got` itself, or the Japanese the game set if the
// widget is showing our Chinese and the reader is not the widget system.
const char* DisplayOnGet(void* self, const char* got, const void* caller);

struct DisplayStats {
    bool on;
    uint32_t entries;        // strings in the table
    uint64_t whole;          // replacements of a whole text
    uint64_t names;          // texts with at least one name replaced
    uint64_t guard_hits;     // reads handed the Japanese back
    uint64_t guard_full;     // replacements refused: nowhere to remember them
    uint64_t too_long;       // texts not examined at all
    uint32_t guarded;        // widgets currently showing our Chinese
    char status[96];
};
DisplayStats DisplayGetStats();

// Up to `max` distinct call sites (RVAs) that were handed the Japanese back.
size_t DisplayGuardCallers(uint32_t* out, size_t max);

// For the self-test: forget the table and every remembered widget.
void DisplayResetForTest();

}  // namespace cielzh
