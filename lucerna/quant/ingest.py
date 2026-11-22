"""Universal structured-data ingestion.

Returns one or more named tables from a file. Never modifies the source file.
Supported: XLSX, XLS (all worksheets, multiple tables per sheet separated by blank rows),
CSV/TSV/TXT (delimiter + encoding detection), JSON (records / nested), JSONL,
DOCX tables, and PDF tables (text-based PDFs only, via pdfplumber).
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ENCODINGS = ("utf-8-sig", "utf-8", "cp1256", "cp1252", "latin-1")


class IngestError(Exception):
    pass


@dataclass
class Table:
    name: str
    frame: pd.DataFrame
    notes: list[str] = field(default_factory=list)


def _decode(data: bytes) -> tuple[str, str]:
    for enc in ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise IngestError("Could not decode the text file with UTF-8, Windows-1256, Windows-1252 or Latin-1.")


def _clean_headers(df: pd.DataFrame) -> pd.DataFrame:
    cols, seen = [], {}
    for i, c in enumerate(df.columns):
        name = str(c).strip() if c is not None and str(c).strip() and not str(c).startswith("Unnamed:") else f"column_{i + 1}"
        name = " ".join(name.split())
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        cols.append(name)
    df = df.copy()
    df.columns = cols
    return df


def _read_delimited(data: bytes, ext: str) -> list[Table]:
    text, enc = _decode(data)
    sample = text[:20000]
    if ext == ".tsv":
        sep = "\t"
    else:
        try:
            sep = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            sep = ","
    try:
        df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False, na_values=[""], engine="python")
    except Exception as exc:
        raise IngestError(f"Could not parse the delimited file: {exc}") from exc
    notes = [f"Encoding detected: {enc}; delimiter: {repr(sep)}"]
    return [Table("data", _clean_headers(df), notes)]


def _split_blocks(raw: pd.DataFrame) -> list[pd.DataFrame]:
    """Split a worksheet into tables separated by fully blank rows; the first non-empty row of each block is its header."""
    blank = raw.isna().all(axis=1)
    blocks, start = [], None
    for i, is_blank in enumerate(list(blank) + [True]):
        if not is_blank and start is None:
            start = i
        elif is_blank and start is not None:
            block = raw.iloc[start:i].dropna(axis=1, how="all")
            if len(block) >= 2:
                blocks.append(block)
            start = None
    out = []
    for b in blocks:
        header = [str(x) if pd.notna(x) else None for x in b.iloc[0].tolist()]
        df = pd.DataFrame(b.iloc[1:].values, columns=header)
        out.append(_clean_headers(df))
    return out


def _read_excel(data: bytes, ext: str) -> list[Table]:
    engine = "openpyxl" if ext == ".xlsx" else "xlrd"
    try:
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, dtype=object, engine=engine)
    except Exception as exc:
        raise IngestError(f"Could not open the workbook: {exc}") from exc
    tables = []
    for sheet, raw in sheets.items():
        if raw.dropna(how="all").empty:
            continue
        blocks = _split_blocks(raw)
        for i, df in enumerate(blocks, 1):
            name = sheet if len(blocks) == 1 else f"{sheet} (table {i})"
            notes = [f"Worksheet '{sheet}'"] + ([f"Table {i} of {len(blocks)} detected by blank-row separation"] if len(blocks) > 1 else [])
            tables.append(Table(name, df, notes))
    if not tables:
        raise IngestError("The workbook contains no tables with a header row and at least one data row.")
    return tables


def _read_json(data: bytes, ext: str) -> list[Table]:
    text, _ = _decode(data)
    if ext == ".jsonl":
        rows = []
        for n, line in enumerate(text.splitlines(), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise IngestError(f"Invalid JSON on line {n}: {exc}") from exc
        return [Table("data", _clean_headers(pd.json_normalize(rows)))]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IngestError(f"Invalid JSON: {exc}") from exc
    if isinstance(obj, list):
        return [Table("data", _clean_headers(pd.json_normalize(obj)))]
    if isinstance(obj, dict):
        tables = [Table(str(k), _clean_headers(pd.json_normalize(v))) for k, v in obj.items()
                  if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
        if tables:
            return tables
        return [Table("data", _clean_headers(pd.json_normalize(obj)))]
    raise IngestError("JSON must contain a list of records or an object of record lists.")


def _read_docx_tables(data: bytes) -> list[Table]:
    from docx import Document
    doc = Document(io.BytesIO(data))
    tables = []
    for i, t in enumerate(doc.tables, 1):
        rows = [[c.text.strip() for c in r.cells] for r in t.rows]
        if len(rows) >= 2:
            tables.append(Table(f"Word table {i}", _clean_headers(pd.DataFrame(rows[1:], columns=rows[0])), ["Extracted from a Word table"]))
    if not tables:
        raise IngestError("No tables were found in this Word document. For narrative documents use Qualitative Intelligence.")
    return tables


def _read_pdf_tables(data: bytes) -> list[Table]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise IngestError("PDF table extraction needs the 'pdfplumber' package (pip install pdfplumber).") from exc
    tables = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            for ti, t in enumerate(page.extract_tables() or [], 1):
                if t and len(t) >= 2:
                    tables.append(Table(f"PDF page {pno} table {ti}", _clean_headers(pd.DataFrame(t[1:], columns=t[0])),
                                        ["Extracted from PDF layout — verify against the source; PDF table extraction can misalign cells."]))
    if not tables:
        raise IngestError("No tables could be extracted from this PDF. Scanned PDFs need OCR; otherwise export the table to Excel/CSV.")
    return tables


def read_tables(data: bytes, filename: str) -> list[Table]:
    ext = Path(filename).suffix.lower()
    if ext in (".csv", ".tsv", ".txt"):
        tables = _read_delimited(data, ext)
    elif ext in (".xlsx", ".xls"):
        tables = _read_excel(data, ext)
    elif ext in (".json", ".jsonl"):
        tables = _read_json(data, ext)
    elif ext == ".docx":
        tables = _read_docx_tables(data)
    elif ext == ".pdf":
        tables = _read_pdf_tables(data)
    else:
        raise IngestError(f"Unsupported file type {ext}")
    out = []
    for t in tables:
        df = t.frame.dropna(how="all")
        df = df.loc[:, ~df.isna().all()]
        if df.empty:
            continue
        # Store everything as text-or-native; typing happens in profiling with user confirmation.
        df = df.reset_index(drop=True)
        out.append(Table(t.name, df, t.notes))
    if not out:
        raise IngestError("No data rows were found.")
    return out
