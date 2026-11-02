// What the display layer costs the game's own thread.
//
//   bench_hooks.exe <cielzh-text.bin> <scratch dir>
//
// Not part of build.ps1: it reads a real text table, which only exists after a
// build on a machine with the game.  Build it beside the self-test:
//
//   cl /nologo /MT /O2 /DNDEBUG /EHsc /std:c++17 /utf-8 test\bench_hooks.cpp
//      cielzh\trace.cpp cielzh\display.cpp cielzh\hooks.cpp
//
// The hooks are thin: the cost is TraceRecord (the recorder) and DisplayOnSet /
// DisplayOnGet (the display layer), so those are what is timed, with the
// recorder's table filled to what an hour of play leaves in it.  The other
// cost is the automatic dump, which writes the whole table from inside a hook
// -- that is a pause on the game's thread, not a per-call cost, and it is
// timed separately.
#include <windows.h>
#include <cstdio>
#include <cstring>
#include <string>
#include "../cielzh/trace.h"
#include "../cielzh/display.h"

using namespace cielzh;

namespace {

uint8_t g_image[0x1000000];   // stands in for the module base

double Now()
{
    static LARGE_INTEGER f = {};
    if (!f.QuadPart)
        QueryPerformanceFrequency(&f);
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    return double(t.QuadPart) / double(f.QuadPart);
}

volatile uintptr_t g_sink;

}  // namespace

int main(int argc, char** argv)
{
    if (argc != 3) {
        std::printf("usage: bench_hooks <cielzh-text.bin> <scratch dir>\n");
        return 2;
    }
    wchar_t table[MAX_PATH], dir[MAX_PATH], dump[MAX_PATH];
    MultiByteToWideChar(CP_ACP, 0, argv[1], -1, table, MAX_PATH);
    MultiByteToWideChar(CP_ACP, 0, argv[2], -1, dir, MAX_PATH);
    swprintf_s(dump, MAX_PATH, L"%s\\bench-trace.txt", dir);

    TraceInit(g_image);
    DisplayInit(g_image);
    char why[160];
    if (DisplayLoad(table, why, sizeof(why)) != 0) {
        std::printf("table: %s\n", why);
        return 1;
    }
    std::printf("table      %s\n", DisplayGetStats().status);

    // What the two hot call sites carry, at the lengths the trace showed --
    // the snapshot stops at 95 bytes, so the long one is made longer still.
    std::string help = "\xE2\x97\x8F\xE5\xBF\xAB\xE6\x8D\xB7\xE6\x96\xB9\xE5\xBC\x8F ";
    while (help.size() < 600)
        help += "\xE3\x80\x80\xE3\x83\xBB\xE8\xAE\xBE\xE7\xBD\xAE\xEF\xBC\x88"
                "\xE6\x89\xB3\xE6\x89\x8B\xEF\xBC\x89 ";
    const char* number = "37";
    const std::string plate = "<CLY2>\xE3\x82\xA4\xE3\x82\xAA\xE3\x83\xB3";   // <CLY2>イオン

    // Fill the recorder to an hour's worth of distinct records.
    char key[64];
    void* caller = g_image + 0x7CC95E;
    for (int i = 0; i < 7000; ++i) {
        std::snprintf(key, sizeof(key), "filler record %d", i);
        TraceRecord(Op::kSet, Klass::kSpriteText,
                    reinterpret_cast<void*>(0x10000 + i * 64), caller, key);
    }
    std::printf("recorder   %llu records held\n",
                (unsigned long long)TraceGetStats().events);

    void* widget = reinterpret_cast<void*>(0x2000);
    void* ui_reader = g_image + 0x962FC0;
    std::string scratch;
    const int N = 400000;

    // set at 0x7CC95E: the same long text again and again (it folds)
    double t0 = Now();
    for (int i = 0; i < N; ++i) {
        TraceRecord(Op::kSet, Klass::kSpriteText, widget, caller, help.c_str());
        g_sink += reinterpret_cast<uintptr_t>(DisplayOnSet(widget, help.c_str(), scratch));
    }
    const double set_long = (Now() - t0) / N * 1e9;

    t0 = Now();
    for (int i = 0; i < N; ++i) {
        TraceRecord(Op::kSet, Klass::kSpriteText, widget, caller, number);
        g_sink += reinterpret_cast<uintptr_t>(DisplayOnSet(widget, number, scratch));
    }
    const double set_short = (Now() - t0) / N * 1e9;

    void* plate_widget = reinterpret_cast<void*>(0x3000);
    t0 = Now();
    for (int i = 0; i < N; ++i) {
        TraceRecord(Op::kSet, Klass::kSpriteText, plate_widget, caller, plate.c_str());
        g_sink += reinterpret_cast<uintptr_t>(DisplayOnSet(plate_widget, plate.c_str(), scratch));
    }
    const double set_name = (Now() - t0) / N * 1e9;

    // get at 0x962FC0: the widget system drawing it, every frame
    const char* shown = DisplayOnSet(plate_widget, plate.c_str(), scratch);
    std::string shown_copy = shown;
    t0 = Now();
    for (int i = 0; i < N; ++i) {
        TraceRecord(Op::kGet, Klass::kSpriteText, plate_widget, ui_reader, shown_copy.c_str());
        g_sink += reinterpret_cast<uintptr_t>(DisplayOnGet(plate_widget, shown_copy.c_str(), ui_reader));
    }
    const double get_ui = (Now() - t0) / N * 1e9;

    std::printf("\nper call (ns)\n");
    std::printf("  set, 600-byte text, no match      %8.0f\n", set_long);
    std::printf("  set, short text                   %8.0f\n", set_short);
    std::printf("  set, nameplate replaced           %8.0f\n", set_name);
    std::printf("  get, drawn by the widget system   %8.0f\n", get_ui);

    // The rates measured in an hour of play: ~178 sets and ~176 gets a second.
    const double per_sec = 178 * set_long + 176 * get_ui;
    std::printf("\nat the measured rates: %.3f ms of the game's thread per second (%.4f%%)\n",
                per_sec / 1e6, per_sec / 1e9 * 100);

    // What a player pays: recording off, display layer only.
    TraceEnable(false);
    t0 = Now();
    for (int i = 0; i < N; ++i) {
        TraceRecord(Op::kSet, Klass::kSpriteText, widget, caller, help.c_str());
        g_sink += reinterpret_cast<uintptr_t>(DisplayOnSet(widget, help.c_str(), scratch));
    }
    const double off_set = (Now() - t0) / N * 1e9;
    t0 = Now();
    for (int i = 0; i < N; ++i) {
        TraceRecord(Op::kGet, Klass::kSpriteText, plate_widget, ui_reader, shown_copy.c_str());
        g_sink += reinterpret_cast<uintptr_t>(DisplayOnGet(plate_widget, shown_copy.c_str(), ui_reader));
    }
    const double off_get = (Now() - t0) / N * 1e9;
    TraceEnable(true);
    const double off_sec = 178 * off_set + 176 * off_get;
    std::printf("\nrecording off (what players get)\n");
    std::printf("  set, 600-byte text                %8.0f ns\n", off_set);
    std::printf("  get, drawn by the widget system   %8.0f ns\n", off_get);
    std::printf("  at the measured rates: %.3f ms per second (%.4f%%), and no dumps\n",
                off_sec / 1e6, off_sec / 1e9 * 100);

    // The dump: written whole from inside a hook.
    double worst = 0, sum = 0;
    for (int i = 0; i < 20; ++i) {
        t0 = Now();
        TraceDump(dump);
        const double ms = (Now() - t0) * 1e3;
        sum += ms;
        if (ms > worst)
            worst = ms;
    }
    WIN32_FILE_ATTRIBUTE_DATA fa = {};
    GetFileAttributesExW(dump, GetFileExInfoStandard, &fa);
    std::printf("\ndump of %llu records: %.1f ms average, %.1f ms worst, %lu KB\n",
                (unsigned long long)TraceGetStats().events, sum / 20, worst,
                fa.nFileSizeLow / 1024);
    DeleteFileW(dump);
    return 0;
}
