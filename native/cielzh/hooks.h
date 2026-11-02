#pragma once
#include <cstddef>

namespace cielzh {

// `size` is a HARD bound on what may be read from `base`, never widened by
// anything the image claims about itself.  0 means "ask the OS", and then each
// range is checked against its own VirtualQuery rather than against one query
// for the first region.  The self-test relies on both behaviours: a one-page
// buffer whose PE header announces 21 MB must be rejected, not believed.
bool VerifyModule(const void* base, size_t size, char* why, size_t why_len);

bool InstallTraceHooks(void* base, char* why, size_t why_len);

// True only if every slot holds its original value again AND every page is back
// to its original protection.  While this is false the DLL must stay loaded: a
// vtable pointing into unmapped code is worse than a hook left running.
//
// Restoring the slots is necessary, not sufficient -- a hook may still be on
// some thread's stack.  Stage one keeps the DLL resident until the process
// exits rather than trying to prove otherwise.
bool RemoveTraceHooks(char* why, size_t why_len);

// Anything at all was written into a vtable, whether or not the install as a
// whole succeeded.  A failed install that wrote one slot must not look clean.
bool HooksTouched();
bool HooksInstalled();

// Recording is live.  Published only after all three slots are in and every
// page is back to read-only, because the three are not one atomic transaction.
bool HooksArmed();

// Hook calls that arrived before arming (or after disarming).  They were
// forwarded to the game untouched and NOT recorded, so a non-zero count means
// the sample has a hole in it and the log should say so.
unsigned long HooksEarlyCalls();

// Test seam: lets the self-test make the second VirtualProtect fail, which is
// the one ordering bug that cannot be reached any other way.  0 restores the
// real function.
using ProtectFn = int (*)(void* addr, size_t len, unsigned long want,
                          unsigned long* old);
void SetProtectForTest(ProtectFn fn);

}  // namespace cielzh
