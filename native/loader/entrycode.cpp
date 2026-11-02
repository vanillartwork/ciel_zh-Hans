// The stub, assembled by hand.
//
// Rules it lives by, each of which came out of getting it wrong first:
//
//  * Only volatile registers (rax, rcx, rdx, r8-r11).  A nonvolatile one would
//    have to be saved and then described in the unwind data.
//  * The saved RCX/RDX of the intercepted call sit ABOVE the argument area, at
//    [rsp+0x38] and [rsp+0x40].  A callee may write [rsp+0x00..0x37] -- both the
//    shadow space and the slots for arguments five to seven -- and the first
//    version of this parked the saved RCX at [rsp+0x20], where WriteFile's
//    fifth argument would have overwritten it with NULL.
//  * Every exit goes through one place that restores RCX/RDX and tail-jumps to
//    the original target, so the game's call happens exactly once.
//  * The path is bounded at every step.  GetModuleFileNameW reports truncation
//    by returning the buffer size, not zero, and appending a file name to a
//    truncated path would both pick the wrong directory and run off the end.
#include "entrycode.h"

#include <cstring>
#include <cstdint>
#include <initializer_list>

namespace cielzh {

namespace {

// A very small assembler.  Once anything overflows it stops writing, and every
// operation checks that first: an earlier version kept patching branch offsets
// and spinning in its alignment loop after the buffer was full.
class Asm {
public:
    Asm(uint8_t* out, size_t cap) : p_(out), cap_(cap) {}

    size_t at() const { return n_; }
    bool ok() const { return ok_; }

    void u8(uint8_t v)
    {
        if (!ok_) return;
        if (n_ + 1 > cap_) { ok_ = false; return; }
        p_[n_++] = v;
    }
    void u32(uint32_t v) { for (int i = 0; i < 4; ++i) u8(uint8_t(v >> (8 * i))); }
    void b(std::initializer_list<uint8_t> bs) { for (uint8_t v : bs) u8(v); }
    void bytes(const void* src, size_t len)
    {
        if (!ok_) return;
        if (n_ + len > cap_) { ok_ = false; return; }
        std::memcpy(p_ + n_, src, len);
        n_ += len;
    }
    void align(size_t to)
    {
        while (ok_ && (n_ % to))
            u8(0xCC);
    }

    // A rip-relative or rel32 displacement, filled in once the RVA is known.
    //
    // `trailing` is how many more bytes of the instruction follow the
    // displacement.  RIP is the address of the NEXT instruction, so a form like
    // `mov dword ptr [rip+d], imm32` has four immediate bytes after the
    // displacement and would otherwise point four bytes short -- which is what
    // silently redirected every status store into the middle of a neighbour.
    void rip(uint32_t target_rva, uint32_t trailing = 0)
    {
        if (!ok_) return;
        if (nfix_ >= kMaxFix) { ok_ = false; return; }
        fix_at_[nfix_] = n_;
        fix_to_[nfix_] = target_rva;
        fix_tail_[nfix_] = trailing;
        ++nfix_;
        u32(0);
    }
    bool resolve(uint32_t block_rva)
    {
        if (!ok_) return false;
        for (size_t i = 0; i < nfix_; ++i) {
            // Wide arithmetic, then a range check: a displacement that does not
            // fit in int32 has to be a refusal, not a silent wrap.
            int64_t end = int64_t(block_rva) + int64_t(fix_at_[i]) + 4
                          + int64_t(fix_tail_[i]);
            int64_t d = int64_t(fix_to_[i]) - end;
            if (d < INT32_MIN || d > INT32_MAX) { ok_ = false; return false; }
            int32_t d32 = int32_t(d);
            std::memcpy(p_ + fix_at_[i], &d32, 4);
        }
        return true;
    }

    size_t here() const { return n_; }
    void j8(uint8_t op, size_t* slot) { u8(op); *slot = n_; u8(0); }
    void j32(std::initializer_list<uint8_t> op, size_t* slot)
    {
        for (uint8_t v : op) u8(v);
        *slot = n_;
        u32(0);
    }
    void back8(uint8_t op, size_t target)
    {
        u8(op);
        int64_t d = int64_t(target) - int64_t(n_ + 1);
        if (d < -128 || d > 127) { ok_ = false; u8(0); return; }
        u8(uint8_t(int8_t(d)));
    }
    void land8(size_t slot)
    {
        if (!ok_) return;
        if (slot >= n_ || slot >= cap_) { ok_ = false; return; }
        int64_t d = int64_t(n_) - int64_t(slot + 1);
        if (d < -128 || d > 127) { ok_ = false; return; }
        p_[slot] = uint8_t(int8_t(d));
    }
    void land32(size_t slot)
    {
        if (!ok_) return;
        if (slot + 4 > n_ || slot + 4 > cap_) { ok_ = false; return; }
        int64_t d = int64_t(n_) - int64_t(slot + 4);
        if (d < INT32_MIN || d > INT32_MAX) { ok_ = false; return; }
        int32_t d32 = int32_t(d);
        std::memcpy(p_ + slot, &d32, 4);
    }

private:
    static constexpr size_t kMaxFix = 96;
    uint8_t* p_;
    size_t cap_;
    size_t n_ = 0;
    bool ok_ = true;
    size_t fix_at_[kMaxFix] = {};
    uint32_t fix_to_[kMaxFix] = {};
    uint32_t fix_tail_[kMaxFix] = {};
    size_t nfix_ = 0;
};

constexpr wchar_t kDllName[] = L"cielzh.dll";
constexpr wchar_t kLogName[] = L"cielzh-loader.log";
constexpr char kAbiSym[] = "CielZhAbiVersion";
constexpr char kInitSym[] = "CielZhInitializeV1";
constexpr char kTagMissing[] = "cielzh loader=missing err=";
constexpr char kTagAbi[] = "cielzh loader=abi ver=";
constexpr char kTagRc[] = "cielzh loader=rc=";

// mov dword ptr [rip+d], imm32
void StoreImm(Asm& a, uint32_t target_rva, uint32_t value)
{
    a.b({0xC7, 0x05});
    a.rip(target_rva, /*trailing=*/4);
    a.u32(value);
}

}  // namespace

bool EmitEntry(const EntryLayout& L, uint8_t* out, size_t cap, EmitResult* res)
{
    if (!out || !res)
        return false;
    if (!L.code_rva || !L.data_rva || !L.orig_target_rva
        || !L.iat_get_module_file_name_w || !L.iat_load_library_ex_w
        || !L.iat_get_proc_address || !L.iat_create_file_w
        || !L.iat_write_file || !L.iat_close_handle || !L.iat_get_last_error)
        return false;

    uint8_t buf[kEntryCodeMax];
    Asm a(buf, sizeof(buf));
    const uint32_t C = L.code_rva;
    const uint32_t D = L.data_rva;

    // ---- literals, so their RVAs are known while emitting code -------------
    const uint32_t o_dll = uint32_t(a.at());   a.bytes(kDllName, sizeof(kDllName));
    const uint32_t o_log = uint32_t(a.at());   a.bytes(kLogName, sizeof(kLogName));
    const uint32_t o_abi = uint32_t(a.at());   a.bytes(kAbiSym, sizeof(kAbiSym));
    const uint32_t o_ini = uint32_t(a.at());   a.bytes(kInitSym, sizeof(kInitSym));
    const uint32_t o_tmiss = uint32_t(a.at()); a.bytes(kTagMissing, sizeof(kTagMissing));
    const uint32_t o_tabi = uint32_t(a.at());  a.bytes(kTagAbi, sizeof(kTagAbi));
    const uint32_t o_trc = uint32_t(a.at());   a.bytes(kTagRc, sizeof(kTagRc));
    const uint32_t o_hex = uint32_t(a.at());   a.bytes("0123456789ABCDEF", 16);
    a.align(16);

    // ---- CopyW(rcx = dest, edx = index, r8 = src, r9d = capacity) ----------
    // Returns the new index in eax.  A leaf: no stack, no calls, no unwind data.
    // The capacity check is a backstop -- the caller already refuses a path that
    // would not fit -- but a copy loop with no bound is not something to leave
    // in a stub that runs inside somebody else's process.
    const uint32_t o_copyw = uint32_t(a.at());
    a.b({0x89, 0xD0});                              // mov eax, edx
    size_t cw_loop = a.here();
    a.b({0x44, 0x39, 0xC8});                        // cmp eax, r9d
    size_t cw_full;
    a.j8(0x73, &cw_full);                           // jae end
    a.b({0x66, 0x45, 0x8B, 0x10});                  // mov r10w, [r8]
    a.b({0x66, 0x44, 0x89, 0x14, 0x41});            // mov [rcx+rax*2], r10w
    a.b({0x66, 0x45, 0x85, 0xD2});                  // test r10w, r10w
    size_t cw_end;
    a.j8(0x74, &cw_end);                            // jz end
    a.b({0xFF, 0xC0});                              // inc eax
    a.b({0x49, 0x83, 0xC0, 0x02});                  // add r8, 2
    a.back8(0xEB, cw_loop);
    a.land8(cw_full);
    a.land8(cw_end);
    a.u8(0xC3);                                     // ret
    a.align(16);

    // ---- Log(rcx = tag, edx = number) -------------------------------------
    // Frame 0x58: shadow 0x20, args 5-7 at 0x20..0x37, saved tag 0x38, saved
    // number 0x40, line length 0x48, file handle 0x50.  CreateFileW takes seven
    // arguments, which is what sizes the argument area.
    //
    // Only ever called once the log path has been built.  The paths that cannot
    // build one do not come here: they leave their verdict in data::kStatus,
    // because writing to an empty file name is not logging.
    const uint32_t o_logfn = uint32_t(a.at());
    a.b({0x48, 0x83, 0xEC, 0x58});
    a.b({0x48, 0x89, 0x4C, 0x24, 0x38});            // mov [rsp+0x38], rcx
    a.b({0x48, 0x89, 0x54, 0x24, 0x40});            // mov [rsp+0x40], rdx
    const uint32_t o_log_body = uint32_t(a.at());

    a.b({0x4C, 0x8B, 0x44, 0x24, 0x38});            // mov r8, [rsp+0x38]
    a.b({0x48, 0x8D, 0x15}); a.rip(D + data::kLine);
    a.b({0x45, 0x31, 0xC9});                        // xor r9d, r9d
    size_t tg_loop = a.here();
    a.b({0x41, 0x8A, 0x00});                        // mov al, [r8]
    a.b({0x84, 0xC0});
    size_t tg_end;
    a.j8(0x74, &tg_end);
    a.b({0x42, 0x88, 0x04, 0x0A});                  // mov [rdx+r9], al
    a.b({0x41, 0xFF, 0xC1});                        // inc r9d
    a.b({0x49, 0x83, 0xC0, 0x01});                  // add r8, 1
    a.back8(0xEB, tg_loop);
    a.land8(tg_end);

    // Eight hex digits, most significant first.  ecx holds the shift because
    // shr needs cl, so the destination index lives in r9d.
    a.b({0x44, 0x8B, 0x54, 0x24, 0x40});            // mov r10d, [rsp+0x40]
    a.b({0x4C, 0x8D, 0x1D}); a.rip(C + o_hex);      // lea r11, [hexdigits]
    a.b({0xB9}); a.u32(28);
    size_t hx_loop = a.here();
    a.b({0x44, 0x89, 0xD0});                        // mov eax, r10d
    a.b({0xD3, 0xE8});                              // shr eax, cl
    a.b({0x83, 0xE0, 0x0F});                        // and eax, 15
    a.b({0x41, 0x8A, 0x04, 0x03});                  // mov al, [r11+rax]
    a.b({0x42, 0x88, 0x04, 0x0A});
    a.b({0x41, 0xFF, 0xC1});
    a.b({0x83, 0xE9, 0x04});                        // sub ecx, 4
    a.back8(0x79, hx_loop);                         // jns loop
    a.b({0xB0, 0x0D}); a.b({0x42, 0x88, 0x04, 0x0A}); a.b({0x41, 0xFF, 0xC1});
    a.b({0xB0, 0x0A}); a.b({0x42, 0x88, 0x04, 0x0A}); a.b({0x41, 0xFF, 0xC1});
    a.b({0x44, 0x89, 0x4C, 0x24, 0x48});            // mov [rsp+0x48], r9d

    a.b({0x48, 0x8D, 0x0D}); a.rip(D + data::kLogPath);
    a.b({0xBA}); a.u32(0x40000000);                 // GENERIC_WRITE
    a.b({0x41, 0xB8}); a.u32(1);                    // FILE_SHARE_READ
    a.b({0x45, 0x31, 0xC9});                        // NULL security attributes
    a.b({0x48, 0xC7, 0x44, 0x24, 0x20}); a.u32(2);  // CREATE_ALWAYS
    a.b({0x48, 0xC7, 0x44, 0x24, 0x28}); a.u32(0x80);
    a.b({0x48, 0xC7, 0x44, 0x24, 0x30}); a.u32(0);
    a.b({0xFF, 0x15}); a.rip(L.iat_create_file_w);
    a.b({0x48, 0x83, 0xF8, 0xFF});                  // cmp rax, -1
    size_t lg_nofile;
    a.j32({0x0F, 0x84}, &lg_nofile);
    a.b({0x48, 0x89, 0x44, 0x24, 0x50});            // mov [rsp+0x50], rax

    a.b({0x48, 0x8B, 0x4C, 0x24, 0x50});
    a.b({0x48, 0x8D, 0x15}); a.rip(D + data::kLine);
    a.b({0x44, 0x8B, 0x44, 0x24, 0x48});            // mov r8d, [rsp+0x48]
    a.b({0x4C, 0x8D, 0x0D}); a.rip(D + data::kWritten);
    a.b({0x48, 0xC7, 0x44, 0x24, 0x20}); a.u32(0);
    a.b({0xFF, 0x15}); a.rip(L.iat_write_file);

    // A write that failed, or wrote less than asked, is not a written log.
    a.b({0x85, 0xC0});                              // test eax, eax
    size_t lg_bad_a;
    a.j32({0x0F, 0x84}, &lg_bad_a);
    a.b({0x8B, 0x05}); a.rip(D + data::kWritten);   // mov eax, [written]
    a.b({0x3B, 0x44, 0x24, 0x48});                  // cmp eax, [rsp+0x48]
    size_t lg_bad_b;
    a.j32({0x0F, 0x85}, &lg_bad_b);
    StoreImm(a, D + data::kLogResult, data::kLogOk);
    size_t lg_close;
    a.j32({0xE9}, &lg_close);
    a.land32(lg_bad_a);
    a.land32(lg_bad_b);
    StoreImm(a, D + data::kLogResult, data::kLogBadWrite);
    a.land32(lg_close);
    a.b({0x48, 0x8B, 0x4C, 0x24, 0x50});
    a.b({0xFF, 0x15}); a.rip(L.iat_close_handle);
    size_t lg_ret;
    a.j32({0xE9}, &lg_ret);
    a.land32(lg_nofile);
    StoreImm(a, D + data::kLogResult, data::kLogNoFile);
    a.land32(lg_ret);
    const uint32_t o_log_epi = uint32_t(a.at());
    a.b({0x48, 0x83, 0xC4, 0x58});
    const uint32_t o_log_tail = uint32_t(a.at());
    a.u8(0xC3);
    const uint32_t log_size = uint32_t(a.at()) - o_logfn;
    a.align(16);

    // ---- Entry ------------------------------------------------------------
    // Frame 0x58: shadow 0x20, args 5-7, saved RCX 0x38, saved RDX 0x40, the
    // directory length 0x48, the module handle 0x50.
    const uint32_t o_entry = uint32_t(a.at());
    a.b({0x48, 0x83, 0xEC, 0x58});
    a.b({0x48, 0x89, 0x4C, 0x24, 0x38});
    a.b({0x48, 0x89, 0x54, 0x24, 0x40});
    const uint32_t o_entry_body = uint32_t(a.at());

    a.b({0x31, 0xC0});                              // xor eax, eax
    a.b({0xB9}); a.u32(1);
    a.b({0xF0, 0x0F, 0xB1, 0x0D}); a.rip(D + data::kTried);
    a.b({0x85, 0xC0});
    size_t to_busy;
    a.j32({0x0F, 0x85}, &to_busy);

    // GetModuleFileNameW(NULL, dllpath, 280)
    a.b({0x31, 0xC9});
    a.b({0x48, 0x8D, 0x15}); a.rip(D + data::kDllPath);
    a.b({0x41, 0xB8}); a.u32(data::kPathChars);
    a.b({0xFF, 0x15}); a.rip(L.iat_get_module_file_name_w);
    a.b({0x85, 0xC0});                              // test eax, eax
    size_t to_pathbad_a;
    a.j32({0x0F, 0x84}, &to_pathbad_a);             // 0 means it failed
    a.b({0x3D}); a.u32(data::kPathChars);           // cmp eax, 280
    size_t to_pathbad_b;
    a.j32({0x0F, 0x83}, &to_pathbad_b);             // jae: returning the size
                                                    // means it was truncated

    // Back up to the last backslash; r9d ends just past it.
    a.b({0x41, 0x89, 0xC1});                        // mov r9d, eax
    a.b({0x48, 0x8D, 0x15}); a.rip(D + data::kDllPath);
    size_t sc_loop = a.here();
    a.b({0x45, 0x85, 0xC9});
    size_t sc_have;
    a.j8(0x74, &sc_have);
    a.b({0x41, 0xFF, 0xC9});                        // dec r9d
    a.b({0x66, 0x42, 0x83, 0x3C, 0x4A, 0x5C});      // cmp word [rdx+r9*2], '\\'
    a.back8(0x75, sc_loop);
    a.b({0x41, 0xFF, 0xC1});                        // inc r9d
    a.land8(sc_have);

    // Room for the longest leaf plus its terminator, checked before any copy.
    a.b({0x41, 0x81, 0xF9}); a.u32(kMaxDirChars);   // cmp r9d, kMaxDirChars
    size_t to_pathbad_c;
    a.j32({0x0F, 0x87}, &to_pathbad_c);             // ja
    a.b({0x44, 0x89, 0x4C, 0x24, 0x48});            // mov [rsp+0x48], r9d

    // logpath = the whole module path, then the leaf replaced.
    a.b({0x48, 0x8D, 0x0D}); a.rip(D + data::kLogPath);
    a.b({0x31, 0xD2});
    a.b({0x4C, 0x8D, 0x05}); a.rip(D + data::kDllPath);
    a.b({0x41, 0xB9}); a.u32(data::kPathChars);     // mov r9d, capacity
    a.b({0xE8}); a.rip(C + o_copyw);
    a.b({0x48, 0x8D, 0x0D}); a.rip(D + data::kLogPath);
    a.b({0x8B, 0x54, 0x24, 0x48});
    a.b({0x4C, 0x8D, 0x05}); a.rip(C + o_log);
    a.b({0x41, 0xB9}); a.u32(data::kPathChars);
    a.b({0xE8}); a.rip(C + o_copyw);

    a.b({0x48, 0x8D, 0x0D}); a.rip(D + data::kDllPath);
    a.b({0x8B, 0x54, 0x24, 0x48});
    a.b({0x4C, 0x8D, 0x05}); a.rip(C + o_dll);
    a.b({0x41, 0xB9}); a.u32(data::kPathChars);
    a.b({0xE8}); a.rip(C + o_copyw);

    // LoadLibraryExW(dllpath, NULL, SEARCH_DLL_LOAD_DIR | SEARCH_SYSTEM32)
    a.b({0x48, 0x8D, 0x0D}); a.rip(D + data::kDllPath);
    a.b({0x31, 0xD2});
    a.b({0x41, 0xB8}); a.u32(0x00000100 | 0x00000800);
    a.b({0xFF, 0x15}); a.rip(L.iat_load_library_ex_w);
    a.b({0x48, 0x85, 0xC0});
    size_t to_missing;
    a.j32({0x0F, 0x84}, &to_missing);
    a.b({0x48, 0x89, 0x44, 0x24, 0x50});

    a.b({0x48, 0x89, 0xC1});                        // mov rcx, rax
    a.b({0x48, 0x8D, 0x15}); a.rip(C + o_abi);
    a.b({0xFF, 0x15}); a.rip(L.iat_get_proc_address);
    a.b({0x48, 0x85, 0xC0});
    size_t to_abi_a;
    a.j32({0x0F, 0x84}, &to_abi_a);
    a.b({0xFF, 0xD0});                              // call rax

    // Compare the major only, which is what the ABI promises; the whole word is
    // kept in eax so the log still shows what was actually there.
    a.b({0x41, 0x89, 0xC2});                        // mov r10d, eax
    a.b({0x41, 0xC1, 0xEA, 0x10});                  // shr r10d, 16
    a.b({0x41, 0x83, 0xFA, uint8_t(kAbiMajorExpected)});
    size_t to_abi_b;
    a.j32({0x0F, 0x85}, &to_abi_b);

    a.b({0x48, 0x8B, 0x4C, 0x24, 0x50});
    a.b({0x48, 0x8D, 0x15}); a.rip(C + o_ini);
    a.b({0xFF, 0x15}); a.rip(L.iat_get_proc_address);
    a.b({0x48, 0x85, 0xC0});
    size_t to_abi_c;
    a.j32({0x0F, 0x84}, &to_abi_c);

    a.b({0x48, 0x8D, 0x0D}); a.rip(D + data::kWhy);
    a.b({0xBA}); a.u32(data::kWhyBytes);
    a.b({0xFF, 0xD0});                              // call rax
    a.b({0x89, 0x05}); a.rip(D + data::kInitRc);
    StoreImm(a, D + data::kStatus, data::kStatusInit);
    a.b({0x8B, 0x05}); a.rip(D + data::kInitRc);    // mov eax, [initrc]
    a.b({0x89, 0xC2});                              // mov edx, eax
    a.b({0x48, 0x8D, 0x0D}); a.rip(C + o_trc);
    a.b({0xE8}); a.rip(C + o_logfn);
    size_t to_done_ok;
    a.j32({0xE9}, &to_done_ok);

    // missing
    a.land32(to_missing);
    StoreImm(a, D + data::kStatus, data::kStatusMissing);
    a.b({0xFF, 0x15}); a.rip(L.iat_get_last_error);
    a.b({0x89, 0xC2});
    a.b({0x48, 0x8D, 0x0D}); a.rip(C + o_tmiss);
    a.b({0xE8}); a.rip(C + o_logfn);
    size_t to_done_miss;
    a.j32({0xE9}, &to_done_miss);

    // abi -- eax still holds whatever version was seen, or 0 for a missing
    // symbol.
    a.land32(to_abi_a);
    a.land32(to_abi_b);
    a.land32(to_abi_c);
    StoreImm(a, D + data::kStatus, data::kStatusAbi);
    a.b({0x89, 0xC2});
    a.b({0x48, 0x8D, 0x0D}); a.rip(C + o_tabi);
    a.b({0xE8}); a.rip(C + o_logfn);
    size_t to_done_abi;
    a.j32({0xE9}, &to_done_abi);

    // No usable path: there is nowhere to write a log, so the status word is
    // the whole record.
    a.land32(to_pathbad_a);
    a.land32(to_pathbad_b);
    a.land32(to_pathbad_c);
    StoreImm(a, D + data::kStatus, data::kStatusPathBad);
    size_t to_done_path;
    a.j32({0xE9}, &to_done_path);

    // Lost the race, or already done: count it and touch nothing else.  Writing
    // a "busy" status here overwrote whatever the first attempt had decided --
    // success, a path failure, an ABI mismatch, a dirty rollback -- and left the
    // process with no record of it.
    a.land32(to_busy);
    a.b({0xF0, 0xFF, 0x05}); a.rip(D + data::kRepeats);   // lock inc [repeats]

    a.land32(to_done_ok);
    a.land32(to_done_miss);
    a.land32(to_done_abi);
    a.land32(to_done_path);
    a.b({0x48, 0x8B, 0x4C, 0x24, 0x38});            // mov rcx, [rsp+0x38]
    a.b({0x48, 0x8B, 0x54, 0x24, 0x40});            // mov rdx, [rsp+0x40]
    const uint32_t o_entry_epi = uint32_t(a.at());
    a.b({0x48, 0x83, 0xC4, 0x58});
    const uint32_t o_entry_tail = uint32_t(a.at());
    a.b({0xE9}); a.rip(L.orig_target_rva);
    const uint32_t entry_size = uint32_t(a.at()) - o_entry;
    a.align(4);

    // ---- unwind information ------------------------------------------------
    // Version 1, no flags, prolog length 4 (the sub rsp), one UWOP_ALLOC_SMALL.
    // Its high nibble is (size/8 - 1): 0x58 is 88 bytes, 88/8 - 1 = 10, so the
    // byte is 0xA2.  0x52 would claim a 48-byte frame and unwind to the wrong
    // place.  No registers are described because none are saved.
    const uint32_t o_unwind_entry = uint32_t(a.at());
    a.b({0x01, 0x04, 0x01, 0x00, 0x04, 0xA2, 0x00, 0x00});
    const uint32_t o_unwind_log = uint32_t(a.at());
    a.b({0x01, 0x04, 0x01, 0x00, 0x04, 0xA2, 0x00, 0x00});

    if (!a.ok() || !a.resolve(C))
        return false;
    if (a.at() > cap)
        return false;

    std::memcpy(out, buf, a.at());
    res->code_bytes = a.at();
    res->entry_offset = o_entry;
    res->entry_size = entry_size;
    res->log_offset = o_logfn;
    res->log_size = log_size;
    res->unwind_entry_offset = o_unwind_entry;
    res->unwind_log_offset = o_unwind_log;
    res->entry_body = o_entry_body;
    res->entry_epilogue = o_entry_epi;
    res->entry_tail = o_entry_tail;
    res->log_body = o_log_body;
    res->log_epilogue = o_log_epi;
    res->log_tail = o_log_tail;
    return true;
}

}  // namespace cielzh
