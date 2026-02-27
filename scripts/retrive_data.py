from typing import Any
from pymongo import MongoClient
from datetime import datetime, timedelta
from bson import ObjectId
from pydantic import BaseModel
from impedance.models.circuits import CustomCircuit
import matplotlib.pyplot as plt
from functools import cached_property
import numpy as np
from pathlib import Path
import pandas as pd
from xrd_analysis import get_phase_summary_from_dara
from traceback import print_exc
import json


client = MongoClient("mongodb://aragorn:27021/")
samples_db = client["Alab_GPSS"]
samples_collection = samples_db["samples"]
experiment_collection = samples_db["experiment"]


# Define the objective function for black-box optimization
def objective(params, frequency, Z):
    # params: [CPE1, w1, CPE2, w2, R1]
    try:
        circuit = CustomCircuit("CPE1-p(CPE2, R1)", initial_guess=params)
        circuit.fit(frequency, Z)
        Z_fit = circuit.predict(frequency)
        # Use normalized RMSE as the objective
        rmse = np.sqrt(np.mean(np.abs((Z - Z_fit) / Z) ** 2))
        # Penalize if fit fails or returns nan
        if np.isnan(rmse) or np.isinf(rmse):
            return 1e6
        return rmse
    except Exception:
        return 1e6


class IonicConductivity(BaseModel):
    measurement_id: str
    timestamp: datetime
    filename: str
    sample_height_mm: float
    sample_diameter_mm: float
    data: dict[str, list[float]]

    def prepare_fitting_data(self):
        frequency = np.array(self.data["Frequency [Hz]"])
        Z = np.array(self.data["Impedance modulus"]) * np.cos(
            np.array(self.data["Impedance phase"])
        ) + 1j * np.array(self.data["Impedance modulus"]) * np.sin(
            np.array(self.data["Impedance phase"])
        )
        return frequency, Z

    @cached_property
    def fitting_impedance(self):
        from scipy.optimize import differential_evolution

        frequency, Z = self.prepare_fitting_data()

        # Reasonable bounds for the parameters (domain knowledge may improve these)
        bounds = [
            (1e-8, 1e-3),  # CPE1
            (0, 1.0),  # w1
            (1e-8, 1e-3),  # CPE2
            (0, 1.0),  # w2
            (1e-1, 1e5),  # R1
        ]

        # Run black-box optimization to find a good initial guess
        result = differential_evolution(
            objective,
            bounds,
            args=(frequency, Z),
            maxiter=20,
            popsize=10,
            polish=True,
            disp=True,
            seed=42,
            workers=-1,  # Use single worker to avoid pickle issues with local functions
        )
        best_guess = result.x
        print("Best initial guess from black-box optimization:", best_guess)

        # Now fit with the best initial guess
        circuit = CustomCircuit("CPE1-p(CPE2, R1)", initial_guess=best_guess)
        circuit.fit(frequency, Z)
        Z_fit = circuit.predict(frequency)
        best_rmse = np.sqrt(np.mean(np.abs((Z - Z_fit) / Z) ** 2))
        print("Final RMSE after fitting:", best_rmse)
        return circuit, best_rmse

    @cached_property
    def ionic_conductivity(self):
        return (
            1
            / self.fitting_impedance[0].parameters_[-1]
            * (self.sample_height_mm / 10)
            / (self.sample_diameter_mm / 20) ** 2
            / np.pi
        )

    def plot_nyquist(self, with_fitting=False):
        frequency, Z = self.prepare_fitting_data()
        plt.plot(Z.real, -Z.imag, label="Measured", marker="o", linestyle="None")
        if with_fitting:
            circuit = self.fitting_impedance[0]
            Z_fit = circuit.predict(frequency)
            plt.plot(Z_fit.real, -Z_fit.imag, label="Fitted")
        plt.legend()
        return plt.gcf()


def find_sample_ids_by_date(date_obj):
    """
    Find all sample['_id'] with a specific date in the 'created_at' field.

    Args:
        date_obj (datetime.date or datetime): The date to match.

    Returns:
        List of ObjectId: List of sample _id values matching the date.
    """
    # Ensure date_obj is a date (not datetime)
    if isinstance(date_obj, datetime):
        date_start = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        date_start = datetime.combine(date_obj, datetime.min.time())
    date_end = date_start + timedelta(days=1)

    query = {"created_at": {"$gte": date_start, "$lt": date_end}}
    results = samples_collection.find(query, {"_id": 1})
    return [doc["_id"] for doc in results]


def get_sample_ids_by_experiment_id(experiment_id):
    """
    Given an experiment_id, return a list of sample _id values associated with that experiment.

    Args:
        experiment_id: The _id of the experiment document.

    Returns:
        List of ObjectId: List of sample _id values linked to the experiment.
    """
    experiment = experiment_collection.find_one({"_id": ObjectId(experiment_id)})
    return [sample["sample_id"] for sample in experiment["samples"]]


def get_ionic_conductivity_data_by_sample_id(sample_id):
    """
    Given a sample_id, return the ionic conductivity data for that sample.
    """
    sample = samples_collection.find_one({"_id": ObjectId(sample_id)})
    if "ionic_conductivity_measurements" in sample["metadata"]:
        return [
            IonicConductivity(**measurement)
            for measurement in sample["metadata"]["ionic_conductivity_measurements"]
            if measurement["sample_height_mm"] is not None
        ]
    else:
        return []


if __name__ == "__main__":
    db = client["HighSpin"]
    collection = db["highSpin"]

    ionic_conductivity_plots_dir = Path(__file__).parent / "ionic_conductivity_plots"
    ionic_conductivity_plots_dir.mkdir(parents=True, exist_ok=True)
    # Ensure XRD plot outputs directory exists
    dara_search_results_plots_dir = Path(__file__).parent / "dara_search_results_plots"
    dara_search_results_plots_dir.mkdir(parents=True, exist_ok=True)

    # Load flagged inspection tracker CSV
    inspection_tracker_path = Path(__file__).parent / "flagged_inspection_tracker.csv"
    if inspection_tracker_path.exists():
        inspection_df = pd.read_csv(inspection_tracker_path)
        # Create a lookup dictionary: (sample_id, measurement_index) -> (status, human_ionic_conductivity)
        inspection_lookup = {}
        for _, row in inspection_df.iterrows():
            key = (str(row["sample_id"]), int(row["measurement_index"]))
            inspection_lookup[key] = {
                "status": row["status"],
                "human_ionic_conductivity": row["human_ionic_conductivity"]
                if pd.notna(row["human_ionic_conductivity"])
                else None,
            }
    else:
        inspection_lookup = {}
        print(
            "Warning: flagged_inspection_tracker.csv not found, proceeding without inspection data"
        )

    all_sample_ids = [
        sample["_id"] for sample in samples_collection.find({"tags": "HiSpin"})
    ]
    has_updated = False
    for sample_id in all_sample_ids:
        sample = samples_collection.find_one({"_id": ObjectId(sample_id)})
        _id = sample["_id"]

        # Check if sample already exists in the mongo collection to avoid duplicates
        if (
            collection.count_documents(
                {
                    "_id": _id,
                    "$or": [
                        {"ionic_conductivity": {"$exists": True}},
                        {"human_ionic_conductivity": {"$exists": True}},
                    ],
                }
            )
            == 0
        ):
            composition = sample["name"].split("_")[0].replace("p", ".")
            if not "heating_profile" in sample.get("metadata", {}):
                continue
            print(f"Processing sample ionic conductivity data for {_id}")

            heating_profile = sample["metadata"]["heating_profile"]
            doc = {
                "_id": _id,
                "composition": composition,
                "heating_profile": heating_profile,
            }

            ionic_conductivity = get_ionic_conductivity_data_by_sample_id(sample["_id"])
            flagged = [ic.fitting_impedance[1] > 1 for ic in ionic_conductivity]

            # Process each measurement
            valid_conductivities = []
            for i, ic in enumerate(ionic_conductivity):
                # Check if this measurement is in the inspection tracker
                inspection_key = (str(_id), i)
                if inspection_key in inspection_lookup:
                    inspection_data = inspection_lookup[inspection_key]
                    # Skip if marked as skipped
                    if inspection_data["status"] == "skipped":
                        print(
                            f"Skipping measurement {i} for sample {_id} (marked as skipped in CSV)"
                        )
                        continue
                    # Use human-provided value if available
                    if inspection_data["human_ionic_conductivity"] is not None:
                        try:
                            human_value = float(
                                inspection_data["human_ionic_conductivity"]
                            )
                            valid_conductivities.append(human_value)
                            print(
                                f"Using human-provided ionic conductivity {human_value} for measurement {i} of sample {_id}"
                            )
                            continue
                        except (ValueError, TypeError):
                            pass  # Fall through to calculated value if conversion fails

                # Plot the measurement
                fig = ic.plot_nyquist(with_fitting=True)
                fig.savefig(
                    ionic_conductivity_plots_dir
                    / f"{'flagged' if flagged[i] else ''}_{_id}_{i}.png"
                )
                plt.close(fig)

                # Use calculated value if not flagged (or if flagged but not in inspection tracker)
                if not flagged[i]:
                    valid_conductivities.append(ic.ionic_conductivity)

            if valid_conductivities:
                doc["ionic_conductivity"] = float(np.mean(valid_conductivities))
            # Insert into MongoDB collection
            collection.update_one({"_id": _id}, {"$set": doc}, upsert=True)
            if "ionic_conductivity" in doc:
                has_updated = True
        if (
            collection.count_documents({"_id": _id, "phase_summary": {"$exists": True}})
            == 0
        ):
            print(f"Processing phase summary for {_id}")
            try:
                phase_summary = get_phase_summary_from_dara(sample["_id"])
                if phase_summary is None:
                    continue
                collection.update_one(
                    {"_id": _id},
                    {"$set": {"phase_summary": phase_summary}},
                    upsert=True,
                )
                has_updated = True
            except Exception as e:
                if "not well-formed" in str(e):
                    raise
                print(f"Error getting phase summary for sample {_id}: {e}")
                print_exc()
