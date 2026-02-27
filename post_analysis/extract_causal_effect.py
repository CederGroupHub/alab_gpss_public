"""Extract causal effects from experiment data using LLM."""

import asyncio
import textwrap
from datetime import datetime
from typing import Literal

import json_repair
import litellm
from monty.serialization import dumpfn, loadfn
from pydantic import BaseModel, Field
import dotenv

dotenv.load_dotenv()


class CasualEffect(BaseModel):
    """Causal effect model extracted from experiment reports."""

    context: str = Field(
        description="The context for the experiment designed. What previous samples it is referred to/compared with/inspired from. Describe the previous experiment done."
    )
    strategy: str = Field(
        description="The strategy used to design experiments, including (1) modifications made to create this composition, (2) adjusted synthesis conditions, and (3) patterns used to propose the composition. Avoid any statement of the estimated effect, such as 'to test', 'to improve', 'to stabilize', etc. Avoid the mentioning of the specific composition formula in the strategy."
    )
    estimated_effect: str = Field(
        description="The estimated effect on the material structures and ionic conductivitity. For example, how the strategy will affect the material phase stability, structure microstructures, and ionic conductivtities."
    )
    actual_effect: str = Field(
        description="The actual effect obtained from the experiment outcome."
    )
    model_agreement: Literal["agree", "partially agree", "disagree"] = Field(
        description="How does the estimated_effect compare to the actual_effect from experiment."
    )
    assumption: str = Field(
        description="The assumptions made by the agent in the statement"
    )


def format_inputs(data):
    """Format experiment data into a text report."""
    composition = data["composition"]
    if data["provenance"] == "human":
        return None
    if "prev_exp" in data:
        prev_exp = data["prev_exp"]
        prev_exp_justification = prev_exp["justification"]
        prev_exp_hypothesis = prev_exp["hypothesis"]

        return textwrap.dedent(
            f"""\
            # Experiemnt design report for {composition}
            ## Hypothesis
            {prev_exp_hypothesis}
            
            ## Rationale for designing this composition
            {prev_exp_justification}

            ## Experiment outcome
            {data["experimental_note"]}
        """
        )
    elif "material_proposal" in data:
        material_proposal = data["material_proposal"]
        justification = material_proposal["justification"]
        return textwrap.dedent(
            f"""\
            # Experiemnt design report for {composition}
            ## Rationale for designing this composition
            {justification}

            ## Experiment outcome
            {data["experimental_note"]}
        """
        )
    else:
        raise ValueError("The format is not recognized.")


async def ask_llm_to_extract(text):
    """Use the GPT-4 model to extract a causal effect using the input prompt."""
    response = await litellm.acompletion(
        model="openai/google/gemini:latest",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a scientific assistant. Given a text report from an experiment (including experiment rationale and outcome), "
                    "extract the experiment strategy, estimated effect, actual effect, and whether the prediction matches outcome. "
                    "Be as concise as possible while preserving the scientific meaning."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Text report:\n{text}\n\n"
                    "Extract the following:\n"
                    "- context: The context for the experiment designed. What previous samples it is referred to/compared with/inspired from.\n"
                    "- strategy: The strategy used to design experiments, including (1) modifications made to create this composition, (2) adjusted synthesis conditions, and (3) patterns used to propose the composition. Avoid any statement of the estimated effect, such as 'to test', 'to improve', 'to stabilize', etc. Avoid the mentioning of the specific composition formula in the strategy.\n"
                    "- estimated_effect: The estimated effect on the material structures and ionic conductivitity. For example, how the strategy will affect the material phase stability, structure microstructures, and ionic conductivtities.\n"
                    "- actual_effect: The actual effect obtained from the experiment outcome.\n"
                    "- model_agreement: How does the estimated_effect compare to the actual_effect from experiment. Choose one of: 'agree', 'partially agree', 'disagree'.\n"
                    "- assumption: The assumptions made by the agent in the statement\n"
                    "Return a JSON with these keys: context, strategy, estimated_effect, actual_effect, model_agreement, assumption."
                ),
            },
        ],
        response_format=CasualEffect
    )
    # Try parsing the LLM output
    try:
        # Assume response["choices"][0]["message"]["content"] contains the assistant's reply
        content = response["choices"][0]["message"]["content"]
        data = json_repair.loads(content)
        return CasualEffect(**data)
    except Exception as e:
        raise RuntimeError(
            f"Failed to extract causal effect: {e}\nLLM response: {content}"
        )


async def process_data(data):
    """Process a single data entry and extract causal effect."""
    text_report = format_inputs(data)
    if text_report is None:
        return None
    result = await ask_llm_to_extract(text_report)
    result = result.model_dump()
    result["sample_id"] = data["sample_id"]
    return result


async def main():
    """Main async function to process all data."""
    # Load data
    all_data = loadfn("hi_spin_tabulated_data_with_metadata.json")

    # Process all data entries
    tasks = [process_data(data) for data in all_data]
    results = await asyncio.gather(*tasks)

    # Filter out None values
    results = [r for r in results if r is not None]

    # Save results
    dt_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    dumpfn(results, f"causal_effects_results_{dt_str}.json")

    print(f"Processed {len(results)} entries. Results saved to causal_effects_results_{dt_str}.json")


if __name__ == "__main__":
    asyncio.run(main())

