# Editing CSV files

[中文](editing-csv.md) | English

Translation CSV files use UTF-8. Fields may contain commas, quotes, and multiple lines. Edit only `zh`, `status`, and `note`; preserve source text and its line breaks.

## Spreadsheet editors

Create a working copy first:

```powershell
py -3 tools/hydrate.py
```

When opening files under `work/zh-Hans/` in LibreOffice Calc or Excel, use text/CSV import, UTF-8, commas as delimiters, and text type for all columns. Disable number/date detection and automatic type conversion. In Calc, also enable treating quoted fields as text.

Save as CSV with `,` as the field delimiter and `"` as the text delimiter. Then synchronize:

```powershell
py -3 tools/dehydrate.py
py -3 tools/validate.py
```

This workflow avoids copying working-file BOM, row-order, or technical-field changes back into the repository.

## Text and web editors

For small changes, a text editor or GitHub's editor is sufficient. When editing repository CSV directly:

- Save UTF-8 without BOM.
- Use LF between records; preserve CRLF inside fields. Do not normalize the whole file's line endings.
- Quote fields with commas or newlines; double embedded quotes as `""`.
- Keep row order and review the diff before submitting.

Run `py -3 tools/validate.py` afterward. See the [data format](translation-data.en.md).
