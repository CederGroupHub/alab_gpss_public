import pymongo
from bson.objectid import ObjectId
from pymatgen.core import Composition, Structure
from dara import search_phases
from dara.structure_db import ICSDDatabase
import tempfile
import os
from pathlib import Path
from monty.serialization import dumpfn, loadfn
from dara import RefinementPhase
from traceback import print_exc


client = pymongo.MongoClient("mongodb://aragorn:27021/")
db = client["Alab_GPSS"]
samples = db["samples"]

SCRIPT_DIR = Path(__file__).resolve().parent
dara_search_folder = SCRIPT_DIR / "dara_search_results"
dara_search_folder.mkdir(parents=True, exist_ok=True)
dara_search_results_plots_dir = SCRIPT_DIR / "dara_search_results_plots"
dara_search_results_plots_dir.mkdir(parents=True, exist_ok=True)


def get_composition_from_sample_id(sample_id) -> Composition:
    sample = samples.find_one({"_id": ObjectId(sample_id)})
    composition = sample["name"].split("_")[0].replace("p", ".")
    return Composition(composition)


def get_xrd_pattern_from_sample_id(sample_id):
    sample = samples.find_one({"_id": ObjectId(sample_id)})
    xrdml_file = sample.get("metadata", {}).get("xrd_measurement", {}).get("xrdml", None)
    if xrdml_file is None:
        return None
    return xrdml_file


def generate_spinel_structure(composition) -> Structure:
    anion_amt = sum(amt for e, amt in composition.items() if not e.is_metal)
    composition /= anion_amt
    composition *= 4
    template_spinel = Structure.from_file(SCRIPT_DIR / "Li2FeCl4.cif")
    template_spinel.remove_oxidation_states()
    li_8a = composition["Li"] / 2 * 0.6
    li_8a = {"Li": li_8a}
    li_16c = composition["Li"] / 2 * 0.4 / 2
    li_16c = {"Li": li_16c}

    metals = {e: amt / 2 for e, amt in composition.items() if e.is_metal and e.symbol != "Li"}
    metals["Li"] = composition["Li"] / 4  # 16 d site

    if sum(metals.values()) > 1:
        sum_metals = sum(metals.values())
        metals = {e: amt / sum_metals for e, amt in metals.items()}
        for e, amt in metals.items():
            li_16c.setdefault(e, 0)
            li_16c[e] += amt * (sum_metals - 1)
    elif sum(li_16c.values()) > 1:
        metals.setdefault("Li", 0)
        metals["Li"] += li_16c["Li"] - 1
        li_16c = {"Li": 1}
    anion = {e: amt / 4 for e, amt in composition.items() if not e.is_metal}
    for site in template_spinel:
        if site.label == "Li1":  # 8 a site
            site.species = Composition(li_8a)
            site.label = "8a"
        elif site.label == "Li2":
            site.species = Composition(li_16c)
            site.label = "16c"
        elif site.label == "Li3" or site.label == "Fe1":
            site.species = Composition(metals)
            site.label = "16d"
        elif site.label == "Cl1":
            site.species = Composition(anion)
            site.label = "4e"
    return template_spinel


def filter_cif_folder(cif_folder: Path):
    for cif_file in cif_folder.glob("*.cif"):
        composition = Composition(cif_file.stem.split("_")[0])
        if all(e.is_metal for e in composition.keys()) or all(not e.is_metal for e in composition.keys()):
            cif_file.unlink()


def get_precursors_from_sample_id(sample_id):
    sample = samples.find_one({"_id": ObjectId(sample_id)})
    precursors = sample.get("metadata", {}).get("powders_dispensed", {})
    return list(Composition(p).reduced_composition for p in precursors.keys())


def dara_search_xrd_pattern(sample_id):
    xrdml_file = get_xrd_pattern_from_sample_id(sample_id)

    if xrdml_file is None:
        return None
    if (dara_search_folder / f"{sample_id}.json").exists():
        return loadfn(dara_search_folder / f"{sample_id}.json")

    precursor_compositions = get_precursors_from_sample_id(sample_id)
    composition = get_composition_from_sample_id(sample_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        xrdml_file_path = os.path.join(temp_dir, "xrdml_file.xrdml")
        with open(xrdml_file_path, "w") as f:
            f.write(xrdml_file)

        structure = generate_spinel_structure(composition)
        structure.to(filename=os.path.join(temp_dir, "spinel.cif"))

        icsd = ICSDDatabase()
        icsd.get_cifs_by_chemsys(composition.chemical_system, dest_dir=Path(temp_dir) / "dara_cifs")
        filter_cif_folder(Path(temp_dir) / "dara_cifs")

        phases = []
        for cif_file in (Path(temp_dir) / "dara_cifs").glob("*.cif"):
            composition = Composition(cif_file.stem.split("_")[0]).reduced_composition
            if composition in precursor_compositions:
                phases.append(RefinementPhase(path=cif_file, params={}))
            else:
                phases.append(RefinementPhase(path=cif_file, params={}))
        phases.append(RefinementPhase(path=Path(temp_dir) / "spinel.cif", params={"b1": "0_0^0.08"}))
    
        print(f"Searching for {sample_id} with {len(phases)} phases")
        
        results = search_phases(
            xrdml_file_path,
            phases,
            max_phases=4,
            phase_params={"gewicht": "SPHAR4", "lattice_range": 0.05},
            rpb_threshold=0.,
            enable_angular_cut=False,
        )

        dumpfn(results, dara_search_folder / f"{sample_id}.json")
        return results


def get_phase_summary_from_dara(sample_id, rwp_threshold=10):
    try:
        dara_result = dara_search_xrd_pattern(sample_id)
    except ValueError as e:
        if "No peaks are detected in the pattern." in str(e):
            return {"phase_summary": {}, "rwp": None, "result_file": None}
        raise

    try:
        if dara_result:
            top_result = dara_result[0].refinement_result
            fig = top_result.visualize()
            (dara_search_results_plots_dir / f"{sample_id}.png").unlink(missing_ok=True)
            fig.write_image(str(dara_search_results_plots_dir / f"{sample_id}.png"))
            fig_json = fig.to_json()
            with open(dara_search_results_plots_dir / f"{sample_id}.plotly.json", "w") as f:
                f.write(fig_json)
    except Exception as e:
        print(f"Error generating XRD plots for sample {sample_id}: {e}")
        print_exc()

    if dara_result is None:
        return None
    top_result = dara_result[0].refinement_result
    weight_fractions = top_result.get_phase_weights()
    new_weight_fractions = {}
    phases = dara_result[0].phases        
    for i, phase in enumerate(weight_fractions):
        if any("spinel" in rp.path.stem for rp in phases[i]):
            new_weight_fractions["spinel"] = weight_fractions[phase]
        else:
            new_weight_fractions[phase] = weight_fractions[phase]

    rwp = float(top_result.lst_data.rwp)
    if rwp > rwp_threshold:
        top_result.visualize().write_image(dara_search_results_plots_dir / f"{sample_id}.png")
    
    return {
        "phase_summary": {k: float(v) for k, v in new_weight_fractions.items()},
        "rwp": rwp,
        "result_file": open(dara_search_folder / f"{sample_id}.json", "r").read()
    }
