

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font

LOG_FILE = "converter.log"


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("csv_to_excel")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    return logger


def fail(logger: logging.Logger, message: str) -> "SystemExit":
    logger.error(message)
    print(f"ERROR: {message}", file=sys.stderr)
    print("See converter.log for details.", file=sys.stderr)
    raise SystemExit(1)


def parse_renames(rename_args, renames_file, logger):
    """Return {old_name: new_name} from --rename flags and/or a JSON file."""
    renames = {}
    if renames_file:
        path = Path(renames_file)
        if not path.is_file():
            fail(logger, f"Renames file not found: {renames_file}")
        try:
            renames = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(logger, f"Renames file is not valid JSON ({renames_file}): {exc}")
        if not isinstance(renames, dict):
            fail(logger, f"Renames file must be a JSON object, e.g. "
                          f'{{\'Full Name\': \'name\'}} ({renames_file})')
    for item in rename_args or []:
        if "=" not in item:
            fail(logger, f'Bad --rename "{item}" — use old=new, '
                         f'e.g. --rename "Full Name=name"')
        old, new = item.split("=", 1)
        renames[old.strip()] = new.strip()
    return renames


def clean(df: pd.DataFrame, date_columns, renames, fill_missing, logger):
    """Clean the dataframe in place; return a dict of what changed."""
    report = {}

    # 1. Tidy column names.
    df.columns = [str(c).strip() for c in df.columns]
    report["columns"] = list(df.columns)

    # 2. Strip whitespace from text cells (object and pandas string dtypes).
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)

    # 3. Drop fully-empty rows, then exact duplicates.
    rows_in = len(df)
    df.dropna(how="all", inplace=True)
    report["empty_rows_dropped"] = rows_in - len(df)
    before = len(df)
    df.drop_duplicates(inplace=True)
    report["duplicate_rows_dropped"] = before - len(df)

    # 4. Rename columns (only ones that exist; warn about the rest).
    if renames:
        missing = [old for old in renames if old not in df.columns]
        for old in missing:
            logger.warning('Rename skipped: no column named "%s"', old)
        df.rename(columns={k: v for k, v in renames.items()
                           if k in df.columns}, inplace=True)
        report["renamed"] = {k: v for k, v in renames.items()
                             if k in df.columns}

    # 5. Parse date columns.
    parsed, unparsed = {}, {}
    for col in date_columns or []:
        if col not in df.columns:
            logger.warning('Date column "%s" not found — skipped', col)
            continue
        before_bad = int(df[col].isna().sum())
        df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
        after_bad = int(df[col].isna().sum())
        parsed[col] = int(df[col].notna().sum())
        unparsed[col] = after_bad - before_bad
        if unparsed[col]:
            logger.warning('%d value(s) in "%s" could not be parsed as dates '
                           "and were left blank", unparsed[col], col)
    report["dates_parsed"] = parsed
    report["dates_unparsed"] = {k: v for k, v in unparsed.items() if v}

    # 6. Missing values: count, then fill (unless --no-fill-missing).
    missing = {c: int(n) for c, n in df.isna().sum().items() if n}
    report["missing_before_fill"] = missing
    if fill_missing and missing:
        for col in df.columns:
            if df[col].isna().any():
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].fillna(df[col].median())
                elif pd.api.types.is_datetime64_any_dtype(df[col]):
                    pass  # leave unparseable dates blank
                else:
                    df[col] = df[col].fillna("")
        logger.info("Filled missing values: %s", missing)

    return df, report


def write_excel(df: pd.DataFrame, output: Path, sheet_name: str,
                logger: logging.Logger) -> None:
    """Write with a bold header row, frozen top row and fitted columns."""
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        sheet = writer.sheets[sheet_name]
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column in sheet.columns:
            width = max((len(str(cell.value)) if cell.value is not None else 0
                         for cell in column), default=10)
            sheet.column_dimensions[column[0].column_letter].width = min(width + 2, 50)
    logger.info("Wrote %s (%d rows x %d cols, sheet %r)",
                output, len(df), len(df.columns), sheet_name)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a CSV file to a cleaned .xlsx file.")
    parser.add_argument("-i", "--input", required=True,
                        help="Input CSV file")
    parser.add_argument("-o", "--output", required=True,
                        help="Output .xlsx file")
    parser.add_argument("--sheet-name", default="Sheet1",
                        help="Worksheet name (default: Sheet1)")
    parser.add_argument("--date-column", action="append", default=[],
                        help="Column to parse as a date (repeatable)")
    parser.add_argument("--rename", action="append", default=[],
                        help='Rename a column: old=new (repeatable), '
                             'e.g. --rename "Full Name=name"')
    parser.add_argument("--renames", default=None,
                        help="JSON file of renames, e.g. {\"Full Name\": \"name\"}")
    parser.add_argument("--no-fill-missing", action="store_true",
                        help="Leave missing values blank instead of filling them")
    args = parser.parse_args(argv)

    logger = setup_logging()
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.is_file():
        fail(logger, f"Input file not found: {args.input}")
    if input_path.suffix.lower() != ".csv":
        logger.warning('Input "%s" does not end in .csv — trying to read it anyway',
                       args.input)
    if output_path.suffix.lower() != ".xlsx":
        fail(logger, f'Output must end in .xlsx, got "{args.output}"')

    renames = parse_renames(args.rename, args.renames, logger)

    try:
        df = pd.read_csv(input_path, dtype=str, keep_default_na=True,
                         na_values=["", "NA", "N/A", "null", "None"])
    except pd.errors.EmptyDataError:
        fail(logger, f"Input file is empty: {args.input}")
    except pd.errors.ParserError as exc:
        fail(logger, f"Could not parse CSV ({args.input}): {exc}")
    except Exception as exc:  # unreadable / permission / encoding
        fail(logger, f"Could not read {args.input}: {exc}")

    if df.empty or len(df.columns) == 0:
        fail(logger, f"No data rows found in {args.input}")

    logger.info("Read %s: %d rows x %d cols", args.input, len(df),
                len(df.columns))

    # Let pandas infer real types (numbers / dates) now that text is raw strings.
    df = df.convert_dtypes()
    for col in df.columns:
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().sum() >= max(1, len(df) // 2) and df[col].notna().any():
            # Only convert when most values are numeric — avoids mangling IDs.
            if numeric.notna().sum() == df[col].notna().sum():
                df[col] = numeric

    df, report = clean(df, args.date_column, renames,
                       fill_missing=not args.no_fill_missing, logger=logger)

    if df.empty:
        fail(logger, "Nothing left after cleaning — all rows were empty/duplicates.")

    try:
        write_excel(df, output_path, args.sheet_name, logger)
    except Exception as exc:
        fail(logger, f"Could not write {args.output}: {exc}")

    warnings = bool(report["dates_unparsed"])
    print("\n--- Conversion summary ---")
    print(f"Input:  {args.input} ({len(df)} rows kept)")
    print(f"Output: {args.output}  (sheet: {args.sheet_name})")
    print(f"Columns: {', '.join(df.columns)}")
    if report["empty_rows_dropped"]:
        print(f"Empty rows dropped: {report['empty_rows_dropped']}")
    if report["duplicate_rows_dropped"]:
        print(f"Duplicate rows dropped: {report['duplicate_rows_dropped']}")
    if report.get("renamed"):
        print(f"Renamed: {report['renamed']}")
    if report["dates_parsed"]:
        print(f"Dates parsed: {report['dates_parsed']}")
    if report["dates_unparsed"]:
        print(f"Dates that could not be parsed: {report['dates_unparsed']}")
    if report["missing_before_fill"]:
        print(f"Missing values filled: {report['missing_before_fill']}")
    print("Full log: converter.log")
    return 2 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
