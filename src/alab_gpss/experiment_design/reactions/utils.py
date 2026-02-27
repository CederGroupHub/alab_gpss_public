"""This module contains utility functions for reaction analysis."""

from itertools import combinations

import numpy as np
from pymatgen.core import Composition

from .parse import parse_material_string


def get_chemical_system(
    compound: str, elements_to_ignore: list[str] = None
) -> list[str]:
    """Given a compound (by name or formula), returns a list of unique elements in the compound.

    Args:
        compound (str): Compound to get elements from
        elements_to_ignore (List[str], optional): List of elements to ignore. Defaults to [].

    Returns:
        List[str]: List of elements present in the compound
    """
    if elements_to_ignore is None:
        elements_to_ignore = []
    result = parse_material_string(compound)["composition"][0]["elements"]
    return [element for element in result if element not in elements_to_ignore]


def get_precursor_sets(
    available_precursors,
    target_products,
    allowed_byproducts=None,
    max_pc=None,
    allow_oxidation=True,
):
    """
    Gather all possible precursor sets for a given target from the available materials.

    Args:
        available_precursors (list): chemical formulae of the compounds that
            may be used as precursors for the targeted synthesis.
        target_products (list): chemical formulae of the desired phase(s)
            to be synthesized.
        allowed_byproducts (list): chemical formulae of any phases that
            may be allowed as secondary products, in addition to the target.
        max_pc (int): maximum number of phases included in each precursor set.
            By default, this will follow the Gibbs phase rule.
        allow_oxidation (bool): whether to allow the inclusion of O2 as a precursor.

    Returns:
        balanced_sets (list): all possible precursor sets.
    """
    # Ensure proper formatting
    if allowed_byproducts is None:
        allowed_byproducts = []
    if isinstance(target_products, str):
        target_products = [target_products]
    if isinstance(allowed_byproducts, str):
        allowed_byproducts = [allowed_byproducts]

    # Get elems in chemical space
    elem_list = []
    for cmpd in available_precursors:
        elems = parse_elements(cmpd)
        elem_list += elems
    elems = list(set(elem_list))

    if not max_pc:
        # Limit set by Gibbs phase rule
        max_pc = len(elems)

    # Enumerate through possible combinations of reactants and products
    # Identify those that result in a balanced rxn
    balanced_sets = []
    for num_pc in range(2, max_pc + 1):
        possible_sets = list(combinations(available_precursors, num_pc))
        if allow_oxidation:
            ox_sets = []
            for solid_set in possible_sets.copy():
                ox_sets.append([*list(solid_set), "O2"])
            possible_sets += ox_sets
        for pc_set in possible_sets:
            trial_soln = get_coeffs(pc_set, target_products)
            if not isinstance(trial_soln, str):  # If reaction can be balanced
                balanced_sets.append([list(pc_set), target_products])
            else:
                for num_byp in range(1, len(allowed_byproducts) + 1):
                    possible_byproducts = combinations(allowed_byproducts, num_byp)
                    for byp_set in possible_byproducts:
                        all_products = target_products + list(byp_set)
                        trial_soln = get_coeffs(pc_set, all_products)
                        if not isinstance(
                            trial_soln, str
                        ):  # If reaction can be balanced
                            balanced_sets.append([list(pc_set), all_products])

    if len(balanced_sets) == 0:
        raise ValueError(
            f"No balanced precursor sets found from the set of precursors {available_precursors} to the set of "
            f"targets+byproducts {target_products + allowed_byproducts }."
        )
    return balanced_sets


def parse_elements(formula):
    """Get unique elements from chemical formula."""
    if "(" in formula:
        cmpd_name = ""
        rform = Composition(formula)
        for e, n in rform.items():
            cmpd_name += str(e) + str(int(n))
        formula = cmpd_name
    letters_only = "".join([letter for letter in formula if letter.isalpha()])
    index = -1
    elems = []
    for letter in letters_only:
        if letter.isupper():
            elems.append(letter)
            index += 1
        else:
            elems[index] += letter
    return list(set(elems))


def get_coeffs(reactants, products):
    """
    Determine whether the specified reactants
    can be balanced to yield the specified products.

    If yes, return balanced coefficients.

    Otherwise, return an appropriate error message.
    """
    num_reacs = len(reactants)

    if isinstance(products, str):
        products = [products]
    elif not isinstance(products, list):
        raise Exception("""Products must be formatted as string or list""")

    # Get sorted list of elems in reactants
    reac_elems = []
    for cmpd in reactants:
        reac_elems += parse_elements(cmpd)
    reac_elems = sorted(set(reac_elems))

    # Get sorted list of elems in products
    prod_elems = []
    for cmpd in products:
        prod_elems += parse_elements(cmpd)
    prod_elems = sorted(set(prod_elems))

    # Normalize first product to 1
    reactants = list(reactants)
    norm_product = products[0]
    if len(products) > 1:
        for cmpd in products[1:]:
            reactants.append(cmpd)

    # Elements in reactants and products must match
    if set(reac_elems) != set(prod_elems):
        return [np.array([0] * len(reactants)), 1000]

    # Form vector with length = num elems in reactants
    elem_vec = []
    for cmpd in reactants:
        elem_vec.extend(parse_elements(cmpd))
    elem_vec = list(set(elem_vec))

    # Form matrix of reactants coefficients
    reac_mat = []
    for i, cmpd in enumerate(reactants):
        reac_mat.append([])
        reac_mat[i] = [0] * len(elem_vec)
        cmpd_comp = Composition(cmpd).as_dict()
        for elem in cmpd_comp:
            for j, check_elem in enumerate(elem_vec):
                if elem == check_elem:
                    reac_mat[i][j] = cmpd_comp[elem]

    # Check rank of matrix
    rank = np.linalg.matrix_rank(reac_mat)
    if rank < len(reactants):  # linearly dependent
        return [np.array([0] * len(reactants)), 1000]

    # Form vector with length = num_elems in products
    prod_vec = [0] * len(elem_vec)
    cmpd_comp = Composition(norm_product).as_dict()
    for elem in cmpd_comp:
        j = 0
        for check_elem in elem_vec:
            if elem == check_elem:
                prod_vec[j] = cmpd_comp[elem]
            j += 1

    A = np.array(reac_mat).transpose()
    b = np.array(prod_vec)

    # Solve linear system using least squares
    soln = (
        np.linalg.lstsq(A, b, rcond=None)[0],
        np.linalg.lstsq(A, b, rcond=None)[1],
    )

    reactant_coeffs = soln[0].flatten()[:num_reacs]
    product_coeffs = np.concatenate(([1.0], soln[0].flatten()[num_reacs:]))

    # Ensure all precursors participate
    if (reactant_coeffs > 1e-6).all():
        # Ensure all byproducts participate
        # Should be produced, not consumed
        if (product_coeffs[1:] < -1e-6).all():
            # Ensure equation is balanced
            tol = 1e-6  # Allow some tolerance
            if (len(soln[1]) == 0) or (soln[1] < tol):
                return [reactant_coeffs, abs(product_coeffs)]
            return "Reaction cannot be balanced"
        return "Not all byproducts are not formed"

    return "Not all precursors participate in the reaction"
