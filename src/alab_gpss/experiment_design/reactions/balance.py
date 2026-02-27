"""This module contains functions for balancing chemical reactions."""

from __future__ import annotations

from reaction_completer import balance_recipe

from .arrows_balancer import balance_recipe_arrows
from .parse import parse_material_string
from .recipe import Recipe


class BalanceError(Exception):
    """An exception raised when the reaction balancer fails."""


def generate_recipe(
    target: str,
    precursor_list: list[str],
    target_mass_g: float | None = None,
    target_mol: float | None = None,
) -> Recipe:
    """
    Generate a recipe for the target material.

    Args:
        target: the target material
        precursor_list: the list of precursor materials
        target_mass_g: the target mass in g
        target_mol: the target mol amount

    Returns:
        the recipe for the target material
    """
    target = parse_material_string(target)

    if target_mass_g is not None and target_mol is not None:
        raise ValueError("Cannot specify both target mass and target mol")
    if target_mass_g is not None:
        target_mol = target_mass_g / target["molmass"]
    elif target_mol is not None:
        pass
    else:
        raise ValueError("No target mol amount or mass was given!")
    if target["material_string"] in precursor_list:
        recipe = Recipe.build_recipe(
            {
                "left": {target["material_string"]: "1"},
                "right": {target["material_string"]: "1"},
            },
            [target],
            target,
        )
    else:
        precursors = [parse_material_string(precursor) for precursor in precursor_list]
        recipe = _balance_recipe_routine(precursors, target)

    return recipe * (target_mol / recipe.target.mol)


def _balance_recipe_routine(precursors: list[dict], target: dict) -> Recipe:
    """Tries the text mining reaction balancer. If this fails, tries the ARROWS balancer."""
    balanced_reaction = None
    try:
        balanced_reaction = balance_recipe(precursors, [target])[0][1]
    except Exception as e:
        print(f"Exception raised in balance_recipe_routine: {e.args[0]}")
        balanced_reaction = None

    if balanced_reaction is None:
        try:
            print(f"Trying ARROWS balancer for {target}...")
            balanced_reaction = balance_recipe_arrows(precursors, [target])[0][1]
            print(f"Balanced reaction: {balanced_reaction}")
        except Exception:
            raise BalanceError(
                "Could not balance reaction with either the text mining or ARROWS balancers!"
            )  # let the last attempt raise

    return Recipe.build_recipe(balanced_reaction, precursors, target)


if __name__ == "__main__":
    print(
        generate_recipe(
            "Na1.25Zr0.5Ge0.5Mg0.5Nb0.5(PO4)3",
            [
                "sodium oxide",
                "NH4H2PO4",
                "ZrO2",
                "SiO2",
                "GeO2",
                "In2O3",
                "MgO",
                "Nb2O5",
            ],
            target_mass_g=4,
        ).calculate_volume_of_ethanol_ul()
    )
