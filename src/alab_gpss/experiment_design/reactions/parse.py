"""This module provides functions for parsing material strings."""

from functools import lru_cache

from material_parser import MaterialParser
from reaction_completer.periodic_table import PT

from ._preparsed_material_strings import PREPARSED

mp = MaterialParser()


class ParserError(Exception):
    """Exception raised for parsing errors."""


class BalanceError(Exception):
    """Exception raised for balance errors."""


### Parsing function stack
#
# we do parsing in multiple steps to work around the parser's limitations:
#   1. check if the string is in the pre-parsed dictionary
#   2. try to parse the string
#   3. if the string fails to parse, try to reformat the formula and parse again
#       - if the string fails to parse again, raise an error
#   4. get the molar mass from the parsing results
#   5. return the answer
#


@lru_cache(maxsize=1024)
def parse_material_string(material_string: str) -> dict:
    """Parse a material string into a dictionary.

    Args:
        material_string (str): the material string to parse

    Returns:
        dict: the parsed material string
    """
    try:
        material_dict = _parse_material_string_routine(material_string)
    except ParserError:
        raise ParserError(f"Could not parse material string {material_string}")
    material_dict["molmass"] = calculate_molmass(material_dict)
    return material_dict


def _parse_material_string_routine(material_string: str) -> dict:
    if material_string in PREPARSED:
        return PREPARSED[material_string]
    try:
        return _parse_material_string_lowlevel(material_string)
    except ParserError:
        pass
    ## dont try/except this, let the error raise on the last attempt
    adjusted = fix_string_for_parser(material_string)
    print(
        f"Parser failed on {material_string}. We modified this to {adjusted} to try again..."
    )
    result = _parse_material_string_lowlevel(adjusted)
    result["material_string"] = material_string
    result["material_formula"] = material_string
    return result


def _parse_material_string_lowlevel(material_string: str) -> dict:
    """Material parser. This is wrapped in a larger routine to parse material names."""
    material_dict = mp.parse_material_string(material_string)
    if not material_dict["material_formula"] or all(
        len(comp["elements"]) == 0 for comp in material_dict["composition"]
    ):
        raise ParserError(f"Could not parse material string {material_string}")

    return material_dict


def calculate_molmass(material_dict: dict) -> float:
    """
    Calculate the molecular mass of a material.

    Args:
        material_dict: the material to calculate the molecular mass

    Returns:
        the molecular mass of the material
    """
    molmass = 0
    for comp in material_dict["composition"]:
        comp_amount = float(comp["amount"])
        for element, amount in comp["elements"].items():
            molmass += (
                float(PT[element]["atomicMass"].split("(")[0])
                * float(amount)
                * comp_amount
            )
    return molmass


def fix_string_for_parser(material_string: str) -> str:
    """The material string parser has problems with certain formulae.
    Specifically, it fails for chemical formulae with neighboring capital letters. We need to insert a 1 between these
    to parse properly.

    Example:
        KNO3 -> K1N1O3

    Args:
        material_string (str): chemical formula

    Returns:
        str: chemical formula, modified for the parser but still equivalent to original
    """
    new_string = ""
    for i, char in enumerate(material_string):
        if char.isupper() and i != 0 and material_string[i - 1].isupper():
            new_string += "1"
        new_string += char
    return new_string
