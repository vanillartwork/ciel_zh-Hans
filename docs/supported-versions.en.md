# Supported game versions

[中文](supported-versions.md) | English

The supported version is the Windows x64 Steam release of Ciel nosurge DX identified as `steam-2025-07`. [data/game-versions.csv](../data/game-versions.csv) records file sizes and SHA-256 hashes.

Compatibility is determined by file hashes. The installer checks the main executable, settings executable, `PACK01.PAK`, and `PACK00_01.PAK`, and stops when compatibility cannot be established.

## Check a local installation

From the repository root:

```powershell
py -3 tools/preflight.py
```

The check covers required files, disk space, and version matches. Unknown versions are reported with their SHA-256 hashes. The patch depends on specific archive layouts, glyph-table locations, and instruction offsets; it cannot be applied unchanged to other versions.

## Adapting to an update

Report an unsupported update through the [installation/runtime issue form](https://github.com/vanillartwork/ciel_zh-Hans/issues/new?template=bug.yml), including check output and hashes.

Maintainers must:

1. Verify the archive format and a byte-identical unchanged rebuild.
2. Reidentify glyph tables, references, and string locations. For the display layer, also verify the loader call site, IAT slots, and vtables checked by the DLL. Synthetic PE tests cannot establish compatibility with a new game version.
3. Extract text, compare IDs and source hashes, and migrate matching translations.
4. Test building, installation, gameplay, and restoration.
5. Update `data/game-versions.csv`.

## Other platforms

Only Windows DX is supported. PS Vita and other releases need separate adaptations; the [format reference](reverse-engineering/README.en.md) may help.
