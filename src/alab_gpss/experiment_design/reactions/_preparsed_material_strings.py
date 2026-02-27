"""The material string parser has problems with certain formulae. To enable the reaction balancing routine, we put
manual parser results here. The parser will cross-reference strings against this dictionary before attempting to parse
the string itself.
"""

from collections import OrderedDict

PREPARSED = {
    "KF": {
        "material_string": "KF",
        "material_name": "Potassium Fluoride",
        "material_formula": "KF",
        "phase": "",
        "additives": [],
        "oxygen_deficiency": None,
        "is_acronym": False,
        "amounts_vars": {},
        "elements_vars": {},
        "composition": [
            {
                "formula": "KF",
                "amount": "1",
                "elements": OrderedDict([("K", 1), ("F", 1)]),
                "species": OrderedDict([("K", 1), ("F", 1)]),
            }
        ],
    }
}
