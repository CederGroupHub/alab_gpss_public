#!/usr/bin/env python3
"""Run reflection workflow for completed samples."""
import asyncio
import json
from pathlib import Path
from copy import deepcopy
from monty.serialization import loadfn
from pymongo import MongoClient
from pymatgen.core import Composition
import rich
from typing import Iterable
from agent_prompts import (
    MaterialDataAbnormalityResult,
    NewExperiment,
    NewMaterialProposal,
    ExperimentDesignWorkflow,
)
from traceback import print_exc
from bson import ObjectId

project_root = Path(__file__).parent.parent
data_path = project_root / "data" / "dataset.json"
data = loadfn(str(data_path))


def safely_get_composition(composition):
    try:
        return Composition(composition)
    except Exception:
        print_exc()
        return None


def remove_sample_id(data: Iterable[dict]) -> list[dict]:
    """Return a deep-copied list with sample_id, batch_number, sample_index, and provenance stripped from each entry."""
    sanitized = deepcopy(list(data))
    for entry in sanitized:
        entry.pop("sample_id", None)
        entry.pop("batch_number", None)
        entry.pop("sample_index", None)
        entry.pop("provenance", None)
    return sanitized


client = MongoClient("mongodb://aragorn:27021/")
db = client["Alab_GPSS"]
collection = db["samples"]

client_2 = MongoClient("mongodb://aragorn:27021/")
db_2 = client_2["HighSpin"]
result_collection = db_2["highSpin"]


def load_result(result):
    if isinstance(result, str):
        result = json.loads(result)
    if isinstance(result, list):
        if "hypothesis" in result[0]["abnormality_results"][0]:  # handle old schema
            hypotheses = [ar.pop("hypothesis") for ar in result[0]["abnormality_results"]]
            new_result = [
                [MaterialDataAbnormalityResult(**ar) for ar in result[0]["abnormality_results"]],
                [[NewExperiment(**{"hypothesis": hypothesis, **ar}) for ar in ar_ if ar.pop("likelihood_high_conductivity", True) or True] for ar_, hypothesis in zip(result[1]["experiments"], hypotheses)],
            ]
        else:
            new_result = [
                [MaterialDataAbnormalityResult(**ar) for ar in result[0]["abnormality_results"]],
                [[NewExperiment(**ar) for ar in ar_ if ar.pop("likelihood_high_conductivity", True) or True] for ar_ in result[1]["experiments"]],
            ]        
    elif isinstance(result, dict):
        new_result = [NewMaterialProposal(**ar) for ar in result["material_proposals"]]
    return new_result


def load_experiment_data(experiment):
    return json.loads(experiment)


async def process_samples():
    """Process all samples that need reflection."""
    for sample in data:
        sample = collection.find_one({"_id": ObjectId(sample["sample_id"]), "tags": "gpt-5-auto"})
        if not sample:
            continue
        if result_collection.find_one(
            {"_id": sample["_id"], "reflection": {"$exists": True}}
        ):
            continue
        if not result_collection.find_one({"_id": sample["_id"]}):
            continue

        prev_result = load_result(sample["metadata"]["result_file"])
        print(prev_result)
        prev_experiment_data = load_experiment_data(
            sample["metadata"]["previous_experiment"]
        )
        workflow = ExperimentDesignWorkflow(data=remove_sample_id(prev_experiment_data))
        composition = sample["name"].replace("p", ".").split("_")[0]
        print(composition)
        new_experiment_data = remove_sample_id(
            [
                d
                for d in data
                if str(d["sample_id"]) == str(sample["_id"])
            ]
        )
        print(new_experiment_data)

        if isinstance(prev_result[0], list):
            exp_mapping = {}
            for i, exps in enumerate(prev_result[1]):
                for exp in exps:
                    try:
                        exp_mapping[Composition(exp.target_composition)] = prev_result[0][i]
                    except Exception:
                        print_exc()
                        continue

            print(exp_mapping)
            prev_abnormality_result = exp_mapping[Composition(composition)]
            prev_exp = [
                ex
                for ex_ in prev_result[1]
                for ex in ex_
                if safely_get_composition(ex.target_composition) == Composition(composition)
                and round(ex.max_heating_temperature / 50) * 50
                == sample["metadata"]["heating_profile"][0][0]
            ][0]
            reflection = await workflow.run_reflection_workflow(
                material_hypothesis=prev_abnormality_result,
                experiment=prev_exp,
                experiment_outcome=new_experiment_data,
            )
        else:
            prev_material_proposal = [
                ar
                for ar in prev_result
                if Composition(ar.composition) == Composition(composition)
            ][0]
            reflection = await workflow.run_reflection_workflow(
                material_hypothesis=prev_material_proposal,
                experiment_outcome=new_experiment_data,
            )

        rich.print(reflection)

        result_collection.update_one(
            {"_id": sample["_id"]}, {"$set": {"reflection": reflection.reflection}}
        )


def main():
    """Main entry point."""
    asyncio.run(process_samples())


if __name__ == "__main__":
    main()
