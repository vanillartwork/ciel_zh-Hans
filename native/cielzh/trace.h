// A bounded record of who sets and who reads UI text.
//
// Stage one answers one question -- which widgets get their text through
// ac::ACText and ac::ACSpriteText, and what reads it back -- so nothing here
// replaces a string.  The getter hook hands back the pointer the game returned,
// untouched; the setter hook forwards the caller's own pointer.
//
// What counts as "the same event" is the part that decides whether the evidence
// is any good.  A menu redrawing every frame must not fill the table, but a
// widget whose text *changes* is the whole point: ネロ -> ？？？ -> ウルゥリィヤ
// has to survive as three records, not one with a count of three.  So the text
// is part of the key, and only a genuinely identical repeat is folded.
//
// Two things follow from that, both of which folded away information once:
//
//   * A snapshot is at most 95 bytes.  Two longer strings sharing a prefix are
//     not known to be equal, so a truncated record never folds -- it would
//     otherwise report one line for text we never finished reading.  The cut is
//     made on a UTF-8 boundary so the snapshot is not half a character.
//   * The thread is part of the key.  "Does anything else touch these objects"
//     is one of the questions stage one exists to answer, and keeping only the
//     first thread's id turned a second thread into +1 on a counter.
//
// first_seq/last_seq/hits summarise calls; they do not reconstruct an ordering.
// Anything needing real sequence wants its own bounded log for that widget.
#pragma once
#include <cstddef>
#include <cstdint>

namespace cielzh {

enum class Op : uint8_t { kSet = 0, kGet = 1 };

// Which vtable the call arrived through.  ACText and ACSpriteText share one
// getter implementation, so the class is only knowable from the slot we hooked.
enum class Klass : uint8_t { kSpriteText = 0, kText = 1 };

struct Event {
    uint64_t first_seq;
    uint64_t last_seq;
    uint64_t object;      // widget address
    uint64_t obs;         // see TraceObserveId
    uint64_t caller_rva;
    uint32_t thread;      // part of the key, not just the first sighting
    uint32_t hits;
    // A hash of the WHOLE text, not just the snapshot, so a long string that
    // repeats folds while two long strings sharing a prefix stay apart.  0 when
    // the text was too long to hash completely; such a record never folds.
    uint64_t full;
    Op op;
    Klass klass;
    bool truncated;       // the snapshot is a prefix; see below
    char text[96];        // snapshot, never the live pointer
};

void TraceInit(const void* module_base);
void TraceRecord(Op op, Klass klass, const void* object, const void* caller,
                 const char* text);

// Recording is a diagnostic, and off for players.
//
// Measured on an hour of real play: the hooks themselves cost the game's thread
// about 0.8 ms a second, but writing the table out took about 50 ms each time,
// from inside a hook, roughly every 12 seconds -- three dropped frames at 60
// fps, again and again, for a file no player reads.  So the display layer runs
// either way, and the recorder only when somebody asks for it (entry.h,
// TraceWanted).  Off, TraceRecord returns before doing anything.
//
// On by default here so the self-test, which drives the recorder directly,
// needs no ceremony; the exported entry point sets it from the marker file.
void TraceEnable(bool on);
bool TraceEnabled();

// An identifier for an address, NOT a lifetime.
//
// Nothing here observes construction or destruction, so a widget that is freed
// and another allocated at the same address are indistinguishable and share an
// id.  Collisions between two live addresses are resolved by probing, so they
// do get different ids -- an earlier version hashed into a single slot and
// handed out a fresh id every time two live objects alternated, which looked
// like churn that was not happening.  Read this as "observation id"; it is not
// evidence about object lifetime and must not be reported as such.
uint64_t TraceObserveId(const void* object);

struct TraceStats {
    uint64_t events;       // distinct records held
    uint64_t calls;        // total hook calls seen
    uint64_t dropped;      // calls not recorded because the table was full
    uint64_t objects;      // distinct addresses seen
    uint64_t objects_lost; // addresses not tracked because that table was full
};

// How this DLL was entered, for the dump header: a run whose log does not say
// how it started is a run nobody can size up afterwards.  This is NOT the
// loader's own outcome -- the loader has its own log and does not call in.
//
// An enum stored atomically, not a string copied into a shared buffer.  The
// exported entry points set this BEFORE reaching the state machine, so two
// callers arriving at once would have been writing the same array with nothing
// ordering them -- a data race even though the bytes they write are identical,
// and outside the very guarantees those entry points promise.  The label is
// resolved to text only while the dump is being written.
enum class Entry : uint32_t {
    kUnknown = 0,
    kExportV1 = 1,
    kSelfTest = 2,
};
void TraceSetEntry(Entry how);
const char* EntryName(Entry how);

TraceStats TraceGetStats();
size_t TraceDrain(Event* out, size_t max);

// 0 on success, non-zero on failure.  A dump that could not be written must not
// look like a dump with nothing in it.
int TraceDump(const wchar_t* path);

// Same, for the way out of the process.
//
// At exit the other threads are already gone, and one of them may have been
// holding the lock when it was killed -- a lock like that is never released, so
// waiting for it would hang the game on the way out.  This gives up instead,
// and the file on disk is then the last automatic dump, whose header says so.
int TraceDumpNoWait(const wchar_t* path);

// Stage one only: writing the table out without anybody asking.
//
// A recorder nothing ever reads is no evidence, and the game has no caller that
// knows when to ask.  The exported dump is for a caller that does.  This covers
// the two cases that matter here: the process exits normally, and the process
// dies -- where a dump written only at exit gives nothing at all, which is the
// run we most need records from.
//
// `path` is written at exit, and again once `every` NEW records have appeared
// and `gap_ms` have passed since the last write.  Only new records count: the
// table already folds an identical repeat, so a settled UI stops writing and a
// changing one keeps the file current.  nullptr turns it off.
//
// Returns 0 when it is on.  The dump header reports it either way: a reader has
// to be able to tell "nothing more happened" from "nobody was writing".
int TraceAutoDump(const wchar_t* path, uint32_t every, uint32_t gap_ms);

struct AutoDumpInfo {
    bool on;
    uint32_t writes;      // automatic dumps attempted
    uint32_t failures;    // of those, the ones that did not land
};
AutoDumpInfo TraceAutoDumpInfo();

// For the self-test only.  The exit dump has to give up rather than hang, and
// there is no way to check that without holding the lock from another thread.
void TraceLockForTest();
void TraceUnlockForTest();

}  // namespace cielzh
