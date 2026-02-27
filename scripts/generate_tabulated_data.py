from __future__ import annotations

import argparse
import hashlib
import json
import logging
import pickle
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from bson import ObjectId
from monty.serialization import loadfn
from pymatgen.core import Composition, Element
from pymatgen.symmetry.groups import SpaceGroup
from pymongo import MongoClient


DEFAULT_LOCAL_URI = "mongodb://aragorn:27021/"
DEFAULT_REMOTE_URI = "mongodb://aragorn:27021/"
DEFAULT_DB = "HighSpin"
DEFAULT_COLLECTION = "highSpin"
REMOTE_DB = "Alab_GPSS"
REMOTE_COLLECTION = "samples"
REFERENCE_DATE = datetime(2025, 11, 1)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "dataset.json"


@dataclass
class XRDAnalysis:
    weight_fractions: Dict[str, float]
    rwp: Optional[str]
    missing_peaks: List[Dict[str, float]]
    extra_peaks: List[Dict[str, float]]


def extract_max_temperature(profile: Any) -> Optional[float]:
    if not isinstance(profile, list):
        return None
    max_temp = None
    for step in profile:
        if isinstance(step, list) and step:
            temp = step[0]
            if temp is not None and (max_temp is None or temp > max_temp):
                max_temp = temp
    return max_temp


def load_refinement_result(result_file_content: str) -> Optional[Any]:
    if not result_file_content:
        return None
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tmpf:
        tmpf.write(result_file_content)
        tmpf.flush()
        return loadfn(tmpf.name)


def normalize_weight_fractions(weight_fractions: Dict[str, float]) -> Dict[str, float]:
    total = sum(weight_fractions.values())
    if total <= 0:
        return {}
    return {k: round(v / total, 4) for k, v in weight_fractions.items()}


def format_weight_fractions(raw_phase_summary: Dict[str, float]) -> Dict[str, float]:
    formatted: Dict[str, float] = {}
    for phase, fraction in raw_phase_summary.items():
        if fraction < 0.01:
            continue
        if phase == "spinel":
            sg_number = 227
            hm = SpaceGroup.from_int_number(sg_number).symbol
            formatted[f"{phase} ({hm})"] = float(fraction)
            continue
        parts = phase.split("_")
        if len(parts) < 2:
            continue
        phase_name = parts[0]
        try:
            sg_number = int(parts[1])
        except ValueError:
            continue
        hm = SpaceGroup.from_int_number(sg_number).symbol
        try:
            comp = Composition(phase_name)
        except Exception:
            continue
        if all(el.is_metal for el in comp) or all(not el.is_metal for el in comp):
            continue
        formatted[f"{phase_name} ({hm})"] = float(fraction)
    return normalize_weight_fractions(formatted)


def build_peak_list(
    peaks: Iterable[Tuple[float, float]], max_intensity: float
) -> List[Dict[str, float]]:
    filtered: List[Dict[str, float]] = []
    if not max_intensity:
        return filtered
    for angle, intensity in peaks:
        rel = intensity / max_intensity
        if rel > 0.05:
            filtered.append(
                {"two_theta": round(angle, 2), "relative_intensity": round(rel, 2)}
            )
    return filtered


_XRD_CACHE_DIR = Path(__file__).parent / ".xrd_cache"


def _get_result_file_hash(result_file_content: str) -> str:
    return hashlib.sha256(result_file_content.encode("utf-8")).hexdigest()


def _get_cache_path(file_hash: str) -> Path:
    if not _XRD_CACHE_DIR.exists():
        _XRD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _XRD_CACHE_DIR / f"xrd_{file_hash}.pkl"


def extract_xrd_analysis(phase_summary: Dict[str, Any]) -> Optional[XRDAnalysis]:
    if not isinstance(phase_summary, dict):
        return None

    refinement_result = None
    result_file_content = phase_summary.get("result_file")
    if isinstance(result_file_content, str):
        file_hash = _get_result_file_hash(result_file_content)
        cache_path = _get_cache_path(file_hash)
        if cache_path.exists():
            try:
                with cache_path.open("rb") as f:
                    cached_analysis = pickle.load(f)
                return cached_analysis
            except Exception as exc:
                logging.warning("Failed to load XRDAnalysis from cache: %s", exc)
                # Proceed to reparse if loading cached result fails

        try:
            refinement_result = load_refinement_result(result_file_content)
        except Exception as exc:
            logging.warning("Failed to load refinement result: %s", exc)

    missing_peaks: List[Dict[str, float]] = []
    extra_peaks: List[Dict[str, float]] = []
    analysis_obj = None
    if refinement_result:
        parsed_results = []
        for refinement in refinement_result:
            try:
                peak_data = refinement.refinement_result.peak_data
                max_intensity = peak_data["intensity"].max().item()
                missing_peaks = build_peak_list(refinement.missing_peaks, max_intensity)
                extra_peaks = build_peak_list(refinement.extra_peaks, max_intensity)
                phases = refinement.phases
                weight_fractions = refinement.refinement_result.get_phase_weights()
                new_weight_fractions = {}
                for i, phase in enumerate(weight_fractions):
                    if any("spinel" in rp.path.stem for rp in phases[i]):
                        new_weight_fractions["spinel"] = weight_fractions[phase]
                    else:
                        new_weight_fractions[phase] = weight_fractions[phase]
                parsed_results.append(
                    {
                        "rwp": f"{refinement.refinement_result.lst_data.rwp:.2f}%",
                        "weight_fractions": new_weight_fractions,
                        "missing_peaks": missing_peaks,
                        "extra_peaks": extra_peaks,
                    }
                )
            except Exception as exc:
                logging.warning("Failed to parse peak data: %s", exc)

        selected_result = None
        for parsed_result in parsed_results:
            wt = parsed_result["weight_fractions"]
            if "spinel" in wt:
                selected_result = parsed_result
                break
        if selected_result is None:
            selected_result = parsed_results[0]
        rwp = selected_result["rwp"]
        raw_weight_fractions = selected_result["weight_fractions"]
        missing_peaks = selected_result["missing_peaks"]
        extra_peaks = selected_result["extra_peaks"]

        weight_fractions = (
            format_weight_fractions(raw_weight_fractions)
            if isinstance(raw_weight_fractions, dict)
            else {}
        )

        analysis_obj = XRDAnalysis(
            weight_fractions=weight_fractions,
            rwp=rwp,
            missing_peaks=missing_peaks,
            extra_peaks=extra_peaks,
        )
        # Save result to cache if possible
        if isinstance(result_file_content, str):
            try:
                file_hash = _get_result_file_hash(result_file_content)
                cache_path = _get_cache_path(file_hash)
                with cache_path.open("wb") as f:
                    pickle.dump(analysis_obj, f)
            except Exception as exc:
                logging.warning("Failed to write XRDAnalysis to cache: %s", exc)

        return analysis_obj


def format_conductivity(value: Any) -> Optional[float]:
    try:
        conductivity = float(value)
    except (TypeError, ValueError):
        return None
    return float(f"{conductivity:.2e}")


def should_skip_sample(composition: Composition, generation_time: datetime) -> bool:
    tz_aware_reference = (
        REFERENCE_DATE
        if generation_time.tzinfo is None
        else REFERENCE_DATE.replace(tzinfo=generation_time.tzinfo)
    )
    if len(composition.elements) > 5 and generation_time < tz_aware_reference:
        return True
    if composition.reduced_composition == Composition("Li3ScCl6").reduced_composition:
        return True
    if Element("Br") in composition.elements or Element("F") in composition.elements:
        return True
    return False


def build_record(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    composition_str = doc.get("composition")
    heating_profile = doc.get("heating_profile")
    if not composition_str or not heating_profile:
        return None

    try:
        pmg_composition = Composition(composition_str)
    except Exception:
        return None

    generation_time = doc["_id"].generation_time
    if should_skip_sample(pmg_composition, generation_time):
        return None

    synthesis_temperature = extract_max_temperature(heating_profile)
    if synthesis_temperature is None:
        return None

    ionic_conductivity = doc.get(
        "human_ionic_conductivity", doc.get("ionic_conductivity")
    )
    ionic_conductivity = format_conductivity(ionic_conductivity)

    phase_summary = doc.get("phase_summary")
    xrd_analysis = extract_xrd_analysis(phase_summary)

    experimental_note = doc.get("reflection")

    if xrd_analysis is None or xrd_analysis.rwp is None or ionic_conductivity is None:
        return None

    return {
        "sample_id": str(doc["_id"]),
        "composition": composition_str,
        "synthesis_temperature": int(synthesis_temperature),
        "xrd_analysis_result": {
            "weight_fractions_of_each_phases": xrd_analysis.weight_fractions,
            "Rwp (%)": xrd_analysis.rwp,
            "missing_peaks": xrd_analysis.missing_peaks,
            "extra_peaks": xrd_analysis.extra_peaks,
        },
        **({"experimental_note": experimental_note} if experimental_note else {}),
        "ionic_conductivity_room_temperature (S/cm)": ionic_conductivity,
    }


def deduplicate_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for record in records:
        key = (record["composition"], record["synthesis_temperature"])
        current_id = record["sample_id"]
        current_time = None
        try:
            current_time = ObjectId(current_id).generation_time
        except Exception:
            pass
        existing = unique.get(key)
        if existing is None:
            unique[key] = record
            continue
        existing_time = None
        try:
            existing_time = ObjectId(existing["sample_id"]).generation_time
        except Exception:
            pass
        if current_time and (not existing_time or current_time > existing_time):
            unique[key] = record
    return list(unique.values())


def fetch_records(mongo_uri: str) -> List[Dict[str, Any]]:
    client = MongoClient(mongo_uri)
    collection = client[DEFAULT_DB][DEFAULT_COLLECTION]
    records = []
    for doc in collection.find({}):
        record = build_record(doc)
        if record:
            records.append(record)
    return records


def summarize_records(records: List[Dict[str, Any]], sample_count: int = 3) -> None:
    print(f"Total records: {len(records)}\n")
    print("Sample records:\n")
    for idx, record in enumerate(records[:sample_count], start=1):
        print(f"Record {idx}:")
        print(json.dumps(record, indent=2))
        print()


def write_json(records: List[Dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(records, f, indent=2)
    print(f"Saved data to {output_path}")


def find_missing_samples(remote_uri: str, existing_ids: set[str]) -> List[List[Any]]:
    client = MongoClient(remote_uri)
    remote_samples = client[REMOTE_DB][REMOTE_COLLECTION]
    missing: List[List[Any]] = []
    for sample in remote_samples.find({"tags": "HiSpin"}):
        sample_id = str(sample["_id"])
        if sample_id in existing_ids:
            continue
        name = sample.get("name", "")
        metadata = sample.get("metadata", {})
        try:
            composition = Composition(name.split("_")[0].replace("p", "."))
        except Exception:
            composition = None
        if "xrd_measurement" not in metadata:
            reason = "No XRD measurement"
        elif "ionic_conductivity_measurements" not in metadata:
            reason = "No ionic conductivity measurement"
        elif "Br" in name:
            reason = "Contains Br"
        elif composition and len(composition.elements) > 5:
            reason = "More than 5 elements"
        else:
            reason = "Unknown"
        missing.append([name, sample["_id"], reason])
    return missing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate HiSpin tabulated data JSON.")
    parser.add_argument(
        "--mongo-uri",
        default=DEFAULT_LOCAL_URI,
        help="MongoDB URI for the HighSpin database.",
    )
    parser.add_argument(
        "--remote-mongo-uri",
        default=DEFAULT_REMOTE_URI,
        help="MongoDB URI for the remote samples database.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output path for the JSON file.",
    )
    parser.add_argument(
        "--skip-remote",
        action="store_true",
        help="Skip fetching missing samples from remote database.",
    )
    parser.add_argument(
        "--sample-count", type=int, default=3, help="Number of sample records to print."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("Connecting to MongoDB...")
    records = fetch_records(args.mongo_uri)
    records = deduplicate_records(records)
    summarize_records(records, args.sample_count)
    write_json(records, args.output)

    if args.skip_remote:
        return

    print("\nFetching missing samples from remote database...")
    missing_samples = find_missing_samples(
        args.remote_mongo_uri, {r["sample_id"] for r in records}
    )
    print(f"Missing sample count: {len(missing_samples)}")
    if missing_samples:
        print(missing_samples[:5])


if __name__ == "__main__":
    main()
