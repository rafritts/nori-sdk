# SPEC-17: Structured Data Tools — JsonRead and CsvRead

## Motivation

Agents working with data pipelines, configuration files, and API responses frequently encounter JSON and CSV. Right now, they use `Bash` with `cat` and `jq` (if available), or `FileRead` and parse in their heads. Neither is great:

- `Bash` + `jq` is not available in all environments and bypasses the sandbox cleanly.
- `FileRead` returns raw text — the agent has to mentally parse structure, which wastes tokens and increases error rates.
- Neither surfaces schema or shape information upfront.

`JsonRead` and `CsvRead` return structured, LLM-friendly representations that give agents the information they actually need — field names, types, row counts, and sampled content — without dumping thousands of tokens of raw data.

---

## JsonRead

Read a JSON file and return its contents in an LLM-friendly format.

```python
JsonRead(path="/app/config.json")
JsonRead(path="/app/results.json", path_expr="$.users[*].email")
JsonRead(path="/app/big.json", summarize=True)
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | str | yes | Path to the JSON file |
| `path_expr` | str | no | JSONPath expression to extract a subset. Uses `jsonpath-ng`. |
| `summarize` | bool | no | If True, return shape/schema info instead of full content. Default: False. |
| `reason` | str | yes | Injected by framework |

### Output modes

**Default (full content):**

Returns pretty-printed JSON, capped at 20,000 characters. If truncated, appends a notice with the total size.

**`path_expr` (filtered):**

Applies the JSONPath expression and returns matching values. Useful for extracting a specific key or list from a large document.

```
$.users[*].email → ["alice@example.com", "bob@example.com", ...]
```

**`summarize=True` (shape report):**

Returns a structural summary instead of content. Designed for large files where the agent needs to understand structure before deciding what to extract.

```
Type: array[847 items]
Item schema (from first 5):
  id: integer
  name: string
  email: string
  created_at: string (ISO 8601)
  tags: array[string]
  address: object
    street: string
    city: string
    zip: string
```

### Error handling

- File not found → error string
- Invalid JSON → error string with parse error message and approximate line number
- JSONPath no match → `"No matches for expression: $.foo.bar"`

---

## CsvRead

Read a CSV file and return its contents in an LLM-friendly format.

```python
CsvRead(path="/data/users.csv")
CsvRead(path="/data/sales.csv", max_rows=20)
CsvRead(path="/data/big.csv", summarize=True)
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | str | yes | Path to the CSV file |
| `max_rows` | int | no | Maximum data rows to return. Default: 50. |
| `summarize` | bool | no | If True, return column stats instead of row data. Default: False. |
| `delimiter` | str | no | Column delimiter. Default: auto-detect (tries `,` then `\t` then `;`). |
| `reason` | str | yes | Injected by framework |

### Output modes

**Default (row data):**

Returns a markdown table of up to `max_rows` rows, with a header row and total row count.

```
Total rows: 1,204 (showing first 50)

| id | name  | email             | created_at |
|----|-------|-------------------|------------|
| 1  | Alice | alice@example.com | 2024-01-15 |
| 2  | Bob   | bob@example.com   | 2024-01-16 |
...
```

**`summarize=True` (column stats):**

Returns per-column statistics instead of rows. Designed for large files.

```
Total rows: 1,204
Columns: 8

| column     | type    | nulls | unique | sample values                    |
|------------|---------|-------|--------|----------------------------------|
| id         | integer | 0     | 1204   | 1, 2, 3                          |
| name       | string  | 0     | 1201   | Alice, Bob, Carol                |
| revenue    | float   | 12    | 844    | 1200.00, 450.50, 8921.75         |
| created_at | string  | 0     | 365    | 2024-01-15, 2024-01-16           |
```

Type inference: integer, float, boolean, date (ISO 8601), datetime, string.

### Error handling

- File not found → error string
- Empty file → `"File is empty"`
- Malformed CSV → best-effort parse with a warning about bad rows

---

## Sandbox

Both tools enforce sandbox via `check_path()` — same as all other file tools.

---

## Dependencies

- `jsonpath-ng` — JSONPath evaluation for `JsonRead`. Lightweight, pure Python.
- No new dependency for `CsvRead` — Python's stdlib `csv` module is sufficient.

---

## What's out of scope

- **Writing JSON/CSV** — `FileWrite` handles this. Agents construct the content as a string and write it.
- **Excel/Parquet/Avro** — out of scope. `Bash` + `python -c` is the escape hatch for exotic formats.
- **In-memory transformation** — these are read tools, not data manipulation tools. If the agent needs to filter or join, it should use `CodeRunner`.
- **JsonWrite / CsvWrite** — not needed. `FileWrite` with a well-formed string is sufficient.

---

## File Layout

```
nori/tools/
    json_read.py     # JsonRead
    csv_read.py      # CsvRead
```

---

## Open Questions

- `jsonpath-ng` vs. `jmespath` — JSONPath is more standard; JMESPath is what AWS uses. `jsonpath-ng` is the right call unless there's a specific reason to use JMESPath. Defaulting to `jsonpath-ng`.

Ready to implement.
