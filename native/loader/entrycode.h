// The machine code that goes into the game's new .cielzh section.
//
// Emitted from here rather than pasted into the PE patcher, so the bytes the
// self-test runs are the bytes that get written into the executable.  Every
// address is an RVA, filled in from a layout the caller supplies: the test
// points them at its own fake IAT and probes, the patcher points them at the
// real ones.
//
// The stub keeps no state in nonvolatile registers -- intermediates live in the
// data block -- so its unwind information is a single stack allocation and
// nothing has to be described as saved.
#pragma once
#include <cstddef>
#include <cstdint>

namespace cielzh {

// Offsets inside the RW data block.  Not on the stack: the entry runs once,
// claimed by an interlocked flag, so a static block is enough, and it keeps the
// stack frame down to what the calling convention needs.
namespace data {
constexpr uint32_t kTried      = 0x000;  // LONG, interlocked
constexpr uint32_t kInitRc     = 0x004;  // LONG, what CielZhInitializeV1 said
constexpr uint32_t kModule     = 0x008;  // HMODULE of cielzh.dll
constexpr uint32_t kWritten    = 0x010;  // DWORD for WriteFile
constexpr uint32_t kStatus     = 0x014;  // DWORD, one of kStatus* below
constexpr uint32_t kLogResult  = 0x018;  // DWORD, one of kLog* below
constexpr uint32_t kDllPath    = 0x020;  // WCHAR[280]
constexpr uint32_t kLogPath    = 0x270;  // WCHAR[280]
constexpr uint32_t kWhy        = 0x4C0;  // char[256], filled by the DLL
constexpr uint32_t kLine       = 0x5C0;  // char[320], the log line being built
constexpr uint32_t kSize       = 0x700;
constexpr uint32_t kPathChars  = 280;
constexpr uint32_t kWhyBytes   = 256;

// What the entry decided.  Written even on the paths that cannot log, which is
// the point of having it: when the module path is unusable there is nowhere to
// put a file, and this word is then the only record.
constexpr uint32_t kStatusNotRun  = 0;
constexpr uint32_t kStatusPathBad = 1;  // no path, truncated, or no room
constexpr uint32_t kStatusMissing = 2;
constexpr uint32_t kStatusAbi     = 3;
constexpr uint32_t kStatusInit    = 4;  // reached the DLL; see kInitRc
// There is no kStatusBusy.  A caller that does not win the one attempt leaves
// every field alone and goes straight to the original call: writing "busy" over
// the first attempt's verdict destroyed the only record of what happened, and
// the repeat-entry test was checking arguments rather than whether the first
// result survived.  Repeat entries are counted in kRepeats instead.
constexpr uint32_t kRepeats    = 0x01C;  // DWORD, interlocked

// Whether the log line reached the disk.  "Tried to log" and "logged" are not
// the same thing, and a test that cannot tell them apart proves neither.
constexpr uint32_t kLogNotTried = 0;
constexpr uint32_t kLogOk       = 1;
constexpr uint32_t kLogNoFile   = 2;  // CreateFileW failed
constexpr uint32_t kLogBadWrite = 3;  // WriteFile failed, or wrote short
}  // namespace data

// The ABI major the stub insists on.  Kept here rather than pulled from abi.h,
// which declares dllexports that have no business in the PE tool; abi.h's
// kAbiMajor and this must agree, and the self-test checks that they do.
constexpr uint32_t kAbiMajorExpected = 1;

// The longest file name appended to the directory, in characters, without the
// terminator.  L"cielzh-loader.log" is 17.
constexpr uint32_t kLongestLeaf = 17;
// Largest directory length the buffer can still take a name onto.
constexpr uint32_t kMaxDirChars = data::kPathChars - kLongestLeaf - 1;

// Where everything is, as RVAs into the image the code will run in.
struct EntryLayout {
    uint32_t code_rva = 0;          // start of the emitted block
    uint32_t data_rva = 0;          // start of the data block
    uint32_t orig_target_rva = 0;   // the call's original destination

    // IAT slots (the address OF the slot, not of the function).
    uint32_t iat_get_module_file_name_w = 0;
    uint32_t iat_load_library_ex_w = 0;
    uint32_t iat_get_proc_address = 0;
    uint32_t iat_create_file_w = 0;
    uint32_t iat_write_file = 0;
    uint32_t iat_close_handle = 0;
    uint32_t iat_get_last_error = 0;
};

// What came out, so the caller can patch the call site and register unwind data.
//
// The instruction boundaries are reported rather than left to be counted.  A
// test that guessed "+8 is past the prologue" was landing on the last byte of a
// five-byte mov, and asking the unwinder about an address that is not an
// instruction boundary measures nothing.
struct EmitResult {
    size_t code_bytes = 0;          // total emitted, including literals
    uint32_t entry_offset = 0;      // offset of the entry point within the block
    uint32_t entry_size = 0;        // extent of the entry function
    uint32_t log_offset = 0;        // offset of the logging helper
    uint32_t log_size = 0;
    uint32_t unwind_entry_offset = 0;  // UNWIND_INFO for the entry function
    uint32_t unwind_log_offset = 0;    // UNWIND_INFO for the helper

    // Instruction boundaries worth aiming an unwind test at, as offsets into
    // the block.  "epilogue" is the `add rsp` that releases the frame, still
    // unexecuted; "tail" is the instruction after it, by which point the frame
    // is gone.
    uint32_t entry_body = 0;
    uint32_t entry_epilogue = 0;
    uint32_t entry_tail = 0;        // the tail jmp
    uint32_t log_body = 0;
    uint32_t log_epilogue = 0;
    uint32_t log_tail = 0;          // the ret
};

// Writes the block into `out`.  Returns false if `cap` is too small, the layout
// is incomplete, or anything overflowed while assembling; `out` is then left
// exactly as it was.  That guarantee is real: everything is built in an
// internal buffer and copied out only once it is known to have worked, because
// the PE side will size a section from this and half a stub in a section is
// worse than no stub.
bool EmitEntry(const EntryLayout& layout, uint8_t* out, size_t cap,
               EmitResult* result);

// Upper bound on what EmitEntry writes, for sizing a buffer.  Deliberately well
// clear of the current output: at 1024 the block had grown to exactly the limit,
// so the next instruction added would have turned into a refusal to emit.  The
// PE section is sized from the actual result, not from this.
constexpr size_t kEntryCodeMax = 4096;

}  // namespace cielzh
