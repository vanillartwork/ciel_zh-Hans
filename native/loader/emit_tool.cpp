// Emits the entry block for a layout the caller computes, and describes what it
// produced.
//
//   emit_entry --code-rva N --data-rva N --target N
//              --iat-gmfn N --iat-lle N --iat-gpa N
//              --iat-cf N --iat-wf N --iat-ch N --iat-gle N
//              --out-bin FILE --out-json FILE
//
// Every number may be decimal or 0x-prefixed.  The PE tool works out the real
// section addresses first and passes them in, because a block emitted for some
// other layout has every rip-relative displacement wrong -- and wrong by an
// amount that looks plausible.
//
// The JSON carries a format version, the layout it was given back verbatim, and
// the length and SHA-256 of the bin, so the reader can refuse a stale pairing
// instead of patching an executable with a block it cannot account for.
#include <windows.h>
#include <bcrypt.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include "entrycode.h"

#pragma comment(lib, "bcrypt.lib")

namespace {

constexpr int kJsonFormat = 1;

bool ParseNum(const char* s, uint32_t* out)
{
    if (!s || !*s)
        return false;
    char* end = nullptr;
    unsigned long long v = std::strtoull(s, &end, 0);
    if (!end || *end || v > 0xFFFFFFFFull)
        return false;
    *out = uint32_t(v);
    return true;
}

bool Sha256(const void* data, size_t len, std::string* hex)
{
    BCRYPT_ALG_HANDLE alg = nullptr;
    if (BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0)
        return false;
    unsigned char digest[32] = {};
    bool ok = BCryptHash(alg, nullptr, 0,
                         const_cast<PUCHAR>(static_cast<const UCHAR*>(data)),
                         ULONG(len), digest, sizeof(digest)) >= 0;
    BCryptCloseAlgorithmProvider(alg, 0);
    if (!ok)
        return false;
    static const char* d = "0123456789abcdef";
    hex->clear();
    for (unsigned char b : digest) {
        hex->push_back(d[b >> 4]);
        hex->push_back(d[b & 15]);
    }
    return true;
}

bool WriteAll(const char* path, const void* data, size_t len)
{
    FILE* f = nullptr;
    if (fopen_s(&f, path, "wb") != 0 || !f)
        return false;
    bool ok = std::fwrite(data, 1, len, f) == len;
    ok = (std::fclose(f) == 0) && ok;
    return ok;
}

}  // namespace

int main(int argc, char** argv)
{
    cielzh::EntryLayout L;
    const char* out_bin = nullptr;
    const char* out_json = nullptr;

    struct Opt { const char* name; uint32_t* field; };
    const Opt opts[] = {
        {"--code-rva", &L.code_rva},
        {"--data-rva", &L.data_rva},
        {"--target", &L.orig_target_rva},
        {"--iat-gmfn", &L.iat_get_module_file_name_w},
        {"--iat-lle", &L.iat_load_library_ex_w},
        {"--iat-gpa", &L.iat_get_proc_address},
        {"--iat-cf", &L.iat_create_file_w},
        {"--iat-wf", &L.iat_write_file},
        {"--iat-ch", &L.iat_close_handle},
        {"--iat-gle", &L.iat_get_last_error},
    };

    for (int i = 1; i < argc; ++i) {
        bool taken = false;
        for (const Opt& o : opts) {
            if (std::strcmp(argv[i], o.name) == 0) {
                if (i + 1 >= argc || !ParseNum(argv[i + 1], o.field)) {
                    std::fprintf(stderr, "bad value for %s\n", o.name);
                    return 2;
                }
                ++i;
                taken = true;
                break;
            }
        }
        if (taken)
            continue;
        if (std::strcmp(argv[i], "--out-bin") == 0 && i + 1 < argc) {
            out_bin = argv[++i];
        } else if (std::strcmp(argv[i], "--out-json") == 0 && i + 1 < argc) {
            out_json = argv[++i];
        } else {
            std::fprintf(stderr, "unexpected argument: %s\n", argv[i]);
            return 2;
        }
    }
    if (!out_bin || !out_json) {
        std::fprintf(stderr, "--out-bin and --out-json are both required\n");
        return 2;
    }

    static uint8_t block[cielzh::kEntryCodeMax];
    cielzh::EmitResult r = {};
    if (!cielzh::EmitEntry(L, block, sizeof(block), &r)) {
        std::fprintf(stderr, "EmitEntry refused this layout\n");
        return 1;
    }

    std::string hex;
    if (!Sha256(block, r.code_bytes, &hex)) {
        std::fprintf(stderr, "could not hash the block\n");
        return 1;
    }

    // Write the bin first: the JSON describes it, so a reader that finds both
    // can always check the pairing.
    if (!WriteAll(out_bin, block, r.code_bytes)) {
        std::fprintf(stderr, "could not write %s\n", out_bin);
        return 1;
    }

    char buf[4096];
    int n = std::snprintf(buf, sizeof(buf),
        "{\n"
        "  \"format\": %d,\n"
        "  \"layout\": {\n"
        "    \"code_rva\": %u,\n"
        "    \"data_rva\": %u,\n"
        "    \"orig_target_rva\": %u,\n"
        "    \"iat_get_module_file_name_w\": %u,\n"
        "    \"iat_load_library_ex_w\": %u,\n"
        "    \"iat_get_proc_address\": %u,\n"
        "    \"iat_create_file_w\": %u,\n"
        "    \"iat_write_file\": %u,\n"
        "    \"iat_close_handle\": %u,\n"
        "    \"iat_get_last_error\": %u\n"
        "  },\n"
        "  \"bin\": { \"bytes\": %zu, \"sha256\": \"%s\" },\n"
        "  \"data_block_size\": %u,\n"
        "  \"abi_major\": %u,\n"
        "  \"result\": {\n"
        "    \"code_bytes\": %zu,\n"
        "    \"entry_offset\": %u,\n"
        "    \"entry_size\": %u,\n"
        "    \"log_offset\": %u,\n"
        "    \"log_size\": %u,\n"
        "    \"unwind_entry_offset\": %u,\n"
        "    \"unwind_log_offset\": %u,\n"
        "    \"entry_body\": %u,\n"
        "    \"entry_epilogue\": %u,\n"
        "    \"entry_tail\": %u,\n"
        "    \"log_body\": %u,\n"
        "    \"log_epilogue\": %u,\n"
        "    \"log_tail\": %u\n"
        "  }\n"
        "}\n",
        kJsonFormat,
        L.code_rva, L.data_rva, L.orig_target_rva,
        L.iat_get_module_file_name_w, L.iat_load_library_ex_w,
        L.iat_get_proc_address, L.iat_create_file_w, L.iat_write_file,
        L.iat_close_handle, L.iat_get_last_error,
        r.code_bytes, hex.c_str(),
        cielzh::data::kSize, cielzh::kAbiMajorExpected,
        r.code_bytes, r.entry_offset, r.entry_size, r.log_offset, r.log_size,
        r.unwind_entry_offset, r.unwind_log_offset,
        r.entry_body, r.entry_epilogue, r.entry_tail,
        r.log_body, r.log_epilogue, r.log_tail);
    if (n <= 0 || size_t(n) >= sizeof(buf)) {
        std::fprintf(stderr, "json did not fit\n");
        return 1;
    }
    if (!WriteAll(out_json, buf, size_t(n))) {
        std::fprintf(stderr, "could not write %s\n", out_json);
        return 1;
    }
    std::printf("emitted %zu bytes, entry at +0x%X, sha256 %s\n",
                r.code_bytes, r.entry_offset, hex.c_str());
    return 0;
}
