"""This module contains classes for defining materials and recipes for experimental reactions."""

from __future__ import annotations

from pydantic import BaseModel, model_validator


class Material(BaseModel):
    """A class for defining materials used in a reaction."""

    name: str
    formula: str
    mol: float
    molmass: float

    @model_validator(mode="before")
    def analyze(cls, values) -> dict:
        """Calculate the mass of the material from the number of moles and the molar mass."""
        values["mass"] = values["mol"] * values["molmass"]
        return values

    @property
    def mass(self) -> float:
        """Return the mass of the material."""
        return self.mol * self.molmass

    def __mul__(self, other: float) -> Material:
        if not isinstance(other, (int, float)):
            raise TypeError("Can only multiply by a number")
        if other < 0:
            raise ValueError("Can only multiply by a positive number")
        return Material(
            formula=self.formula,
            name=self.name,
            mol=self.mol * other,
            molmass=self.molmass,
        )

    def __truediv__(self, other: float) -> Material:
        if not isinstance(other, (int, float)):
            raise TypeError("Can only divide by a number")
        if other < 0:
            raise ValueError("Can only divide by a positive number")
        return Material(
            formula=self.formula,
            name=self.name,
            mol=self.mol / other,
            molmass=self.molmass,
        )

    def __str__(self):
        return (
            f"{self.name} ({self.formula}, {self.mol*1000:.3f} mmol, {self.mass:.4f} g)"
        )

    __repr__ = __str__


class Recipe(BaseModel):
    """A class for defining a recipe for a reaction."""

    precursors: list[Material]
    target: Material
    balanced_reaction: dict[str, dict[str, float]]

    def __mul__(self, other: float) -> Recipe:
        return Recipe(
            precursors=[precursor * other for precursor in self.precursors],
            target=self.target * other,
            balanced_reaction=self.balanced_reaction,
        )

    def __truediv__(self, other: float) -> Recipe:
        return Recipe(
            precursors=[precursor / other for precursor in self.precursors],
            target=self.target / other,
            balanced_reaction=self.balanced_reaction,
        )

    @classmethod
    def build_recipe(
        cls, balanced_reaction: dict, precursor_dict_list: list[dict], target_dict: dict
    ) -> Recipe:
        """Build a recipe from a balanced reaction and a list of precursor and target dictionaries."""
        target = Material(
            formula=target_dict["material_formula"],
            name=target_dict["material_string"],
            mol=float(balanced_reaction["right"][target_dict["material_formula"]]),
            molmass=float(target_dict["molmass"]),
        )
        precursors = []
        for precursor_dict in precursor_dict_list:
            if precursor_dict["material_formula"] in balanced_reaction["left"]:
                precursor = Material(
                    formula=precursor_dict["material_formula"],
                    name=precursor_dict["material_string"],
                    mol=float(
                        balanced_reaction["left"][precursor_dict["material_formula"]]
                    ),
                    molmass=float(precursor_dict["molmass"]),
                )
                precursors.append(precursor)

        return Recipe(
            precursors=precursors, target=target, balanced_reaction=balanced_reaction
        )
