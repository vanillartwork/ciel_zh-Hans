// The state machine behind the exported entry points.
//
// It lives here rather than in dllmain.cpp so the self-test can drive it
// against a synthetic image: the exports themselves only add
// GetModuleHandleW(nullptr), which in a test would be the test executable.
//
// The stage-one run answered "does the init point fire more than once" with
// "not in this run", which is not the same as "never", and it also showed the
// first text traffic arriving on a background thread the main thread had not
// created yet.  So the entries are written for concurrent and repeated callers
// rather than assuming the game calls this once, from one thread.
#pragma once
#include <cstddef>

namespace cielzh {

enum class State { kIdle, kBusy, kReady, kCleanupPending };
State CurrentState();

// 0 ready (or already ready); non-zero refused, with `why` filled.
//
// The split between 4 and 5 is about the process, not about which attempt this
// was: 4 means nothing of ours is in the game any more, 5 means something is.
//
// That is necessary to know before unloading, and not sufficient: a hook may
// still be on some thread's stack even with every slot restored.  Stage one
// keeps the DLL resident until the process exits and does not treat any return
// code as permission to unload.
//
//   1  bad arguments
//   2  no module base
//   3  the executable is not the build this was made for
//   4  installing the hooks failed AND everything was put back
//   5  something of ours is still installed -- first attempt or not.  Keep this
//      DLL loaded, do not retry, and say so.
//   6  another caller is inside initialise or shutdown right now
int InitializeAt(void* base, size_t size, char* why, int why_len);

// 0 once nothing of ours is left in the game's vtables.  Non-zero means the
// caller must keep the DLL loaded.
int ShutdownAll(char* why, int why_len);

bool IsReady();

// Test seam: called while the state is kBusy and the first slot has been
// written, to drive the paths a second caller would take.  0 clears it.
using ReentryFn = void (*)();
void SetReentryForTest(ReentryFn fn);

// <the folder holding `module`>\<name>, for the records this DLL writes beside
// the game's own executable.
//
// false when the path cannot be had or does not fit, and `out` is then left
// empty: the caller runs without automatic dumps rather than writing somewhere
// it guessed.  GetModuleFileNameW reports truncation by returning the buffer
// size it was given, not by failing -- believing the returned length there is
// how a path gets silently cut in half.
bool PathBesideModule(void* module, const wchar_t* name, wchar_t* out,
                      size_t cap);

// Where the recorder writes without being asked, and how often.  Stage one
// wants the records from a run that crashes, which is exactly the run that
// never reaches an exit-time dump.
extern const wchar_t kTraceFileName[];

// Recording happens only when this file is beside the executable.  A file
// rather than a setting because the person who needs it is debugging, and the
// person who does not need it -- every player -- should not be paying for it:
// the automatic dump is a 50 ms pause on the game's thread (trace.h).
extern const wchar_t kTraceMarkerName[];
bool TraceWanted(void* module);

// What the last start of the game made of the display layer, written beside
// the executable on every start: the result of InitializeAt, its reason, and
// the replacement table's state.  Without it a missing or refused table looks
// exactly like a working patch until somebody notices Japanese where Chinese
// should be; install.py --verify reads it back for the player.
extern const wchar_t kStatusFileName[];
bool WriteStatus(void* module, int rc, const char* why);
constexpr unsigned kTraceDumpEvery = 1;      // any new record is worth writing
constexpr unsigned kTraceDumpGapMs = 1500;   // but not more often than this

}  // namespace cielzh
