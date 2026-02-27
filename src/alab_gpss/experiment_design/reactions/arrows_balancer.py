"""An adaptation of the reaction balancing code from ARROWS that can substitute the NLP MaterialParser's balancer."""

from .utils import (
    get_chemical_system,
    get_coeffs,
    get_precursor_sets,
)


def balance_recipe_arrows(
    precursors: list[dict],
    targets: list[dict],
    all_allowed_byproducts: list[str] = None,
):
    """An adaptation of Nathan's reaction balancing code from ARROWS that can substitute the
    NLP MaterialParser"s balancer.

    Args:
        precursors (List[dict]): list of precursors (as outputs from
            alab_one.experimentaldesign.reactions.balance_reaction.parse_material_string)
        targets (List[dict]): target formula (as above, list entry should be an output
            from parse_material_string)
        all_allowed_byproducts (List[str], optional): List of byproduct formulae (as
            strings). Note that byproducts will be filtered to those within the chemical space of our precursors
            Defaults to ["CO2", "NH3", "N2", "O2", "H2", "H2O", "NH4"].

    Returns:
        _type_: _description_
    """
    if all_allowed_byproducts is None:
        all_allowed_byproducts = ["CO2", "NH3", "N2", "O2", "H2", "H2O", "NH4"]

    precursors_ = [precursor["material_formula"] for precursor in precursors]
    targets_ = [target["material_formula"] for target in targets]

    if len(targets_) != 1:
        raise Exception(
            f"Only one target is allowed in the ARROWS reaction balancer; you gave {len(targets_)} ({targets_})!"
        )

    chemical_space = set()
    for precursor in precursors_:
        chemical_space.update(get_chemical_system(precursor))

    allowed_byproducts = [
        byproduct
        for byproduct in all_allowed_byproducts
        if len(set(get_chemical_system(byproduct)) - chemical_space) == 0
    ]  ## only allow byproducts that are fully within the chemical space

    answers = get_precursor_sets(
        available_precursors=precursors_,
        target_products=targets_,
        allowed_byproducts=allowed_byproducts,
    )
    precursors_in_use, products_in_use = answers[0][0], answers[0][1]
    coeff_left, coeff_right = get_coeffs(precursors_in_use, products_in_use)
    balanced_formula = {
        "left": {
            material: round(mol, 5)
            for material, mol in zip(precursors_in_use, coeff_left)
        },
        "right": {
            material: round(mol, 5)
            for material, mol in zip(products_in_use, coeff_right)
        },
    }

    pretty_formula = ""
    for material, mol in balanced_formula["left"].items():
        pretty_formula += f"{mol} {material} + "
    pretty_formula = pretty_formula[:-3] + " == "
    for material, mol in balanced_formula["right"].items():
        pretty_formula += f"{mol} {material} + "
    pretty_formula = pretty_formula[:-3]

    return [
        (targets_[0], balanced_formula, None, pretty_formula)
    ]  # the other format has the balanced rxn in var[0][1]
