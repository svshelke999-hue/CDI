import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


JSON_DATA_DIR = Path(__file__).parent / "JSON_Data"


def find_payer_dirs(base_dir: Path) -> List[Path]:
    payer_dirs: List[Path] = []
    if not base_dir.exists():
        return payer_dirs
    for item in base_dir.iterdir():
        if item.is_dir() and item.name.startswith("extracted_procedures_single_call_"):
            payer_dirs.append(item)
    return sorted(payer_dirs)


def infer_payer_name(payer_dir: Path) -> str:
    # Example: extracted_procedures_single_call_Anthem_with_evidence_v2 -> Anthem
    name = payer_dir.name
    parts = name.split("_")
    try:
        idx = parts.index("call") + 1
        payer = parts[idx]
        # Normalize common casing
        return payer.capitalize()
    except Exception:
        return name


def load_json_safely(path: Path) -> Optional[Dict]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def extract_display_name(proc: Dict) -> str:
    # Prefer procedure_id, then section_title, then first of names, then filename placeholder
    if isinstance(proc, dict):
        if proc.get("procedure_id"):
            return str(proc["procedure_id"])  # already a succinct identifier
        if proc.get("section_title"):
            return str(proc["section_title"])  # may be longer but informative
        names = proc.get("names")
        if isinstance(names, list) and names:
            return str(names[0])
        if proc.get("title"):
            return str(proc["title"])
    return ""


def iterate_matches(
    codes_of_interest: Set[str],
    payer_dirs: Iterable[Path],
) -> List[Tuple[str, str, str, str]]:
    """
    Returns list of tuples: (cpt_code, procedure_display_name, payer_name, source_file)
    """
    results: List[Tuple[str, str, str, str]] = []
    normalized_targets: Set[str] = {c.strip() for c in codes_of_interest if c and c.strip()}

    for payer_dir in payer_dirs:
        payer_name = infer_payer_name(payer_dir)
        for json_file in payer_dir.glob("*.json"):
            data = load_json_safely(json_file)
            if not isinstance(data, dict):
                continue

            codes = data.get("codes")
            if not isinstance(codes, list):
                continue

            display_name = extract_display_name(data) or json_file.stem

            for code_entry in codes:
                if not isinstance(code_entry, dict):
                    continue
                system = str(code_entry.get("system", "")).strip().upper()
                code_value = str(code_entry.get("code", "")).strip()
                if not code_value:
                    continue
                if system != "CPT":
                    continue
                if code_value in normalized_targets:
                    results.append((code_value, display_name, payer_name, json_file.name))

    # De-duplicate while preserving order
    seen: Set[Tuple[str, str, str, str]] = set()
    unique_results: List[Tuple[str, str, str, str]] = []
    for row in results:
        if row not in seen:
            seen.add(row)
            unique_results.append(row)

    # Sort by CPT code, then payer, then procedure display name
    unique_results.sort(key=lambda r: (r[0], r[2], r[1]))
    return unique_results


def write_txt(
    rows: List[Tuple[str, str, str, str]],
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("CPT\tProcedure\tPayer\tSourceFile\n")
        for cpt, proc, payer, src in rows:
            f.write(f"{cpt}\t{proc}\t{payer}\t{src}\n")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a TXT list mapping CPT codes to procedure names/IDs with payer names."
    )
    parser.add_argument(
        "--codes",
        nargs="*",
        help="CPT codes to include (space-separated). Example: --codes 29888 27120",
    )
    parser.add_argument(
        "--codes-file",
        type=str,
        help="Path to a text file with one CPT code per line.",
    )
    parser.add_argument(
        "--out",
        type=str,
        help="Output TXT file path. Default: outputs/cpt_report_<timestamp>.txt",
    )
    return parser.parse_args(argv)


def load_codes_from_file(path: Path) -> List[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    codes: Set[str] = set()
    if args.codes:
        codes.update(str(c).strip() for c in args.codes if str(c).strip())
    if args.codes_file:
        codes.update(load_codes_from_file(Path(args.codes_file)))

    if not codes:
        print(
            "No CPT codes provided. Use --codes or --codes-file to specify codes.",
            file=sys.stderr,
        )
        return 2

    payer_dirs = find_payer_dirs(JSON_DATA_DIR)
    if not payer_dirs:
        print(
            f"No payer directories found under: {JSON_DATA_DIR}",
            file=sys.stderr,
        )
        return 3

    matches = iterate_matches(codes, payer_dirs)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = Path("outputs") / f"cpt_report_{timestamp}.txt"
    out_path = Path(args.out) if args.out else default_out

    write_txt(matches, out_path)

    print(f"Wrote {len(matches)} row(s) -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


