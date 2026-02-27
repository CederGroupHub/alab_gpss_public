from __future__ import annotations

from enum import Enum

from alab_control.labman_dosing_head_rack.labman_dosing_head_rack import (
    DosingHeadRack as LabmanDosingHeadRack,
)
from alab_management.device_view import BaseDevice
from alab_management.device_view.device import mock
from alab_management.sample_view import SamplePosition


class DosingHeadStatus(Enum):
    normal = "normal"
    stuck = "stuck"
    empty = "empty"
    in_use = "in_use"


class DosingHeadRack(BaseDevice):
    description = """A rack that holds all the dosing heads."""

    ALL_SLOTS = [
        f"{slot}{level}" for level in ["A", "B", "C", "D"] for slot in range(1, 15)
    ]

    def __init__(self, firmware_version: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.firmware_version = firmware_version
        self.dosing_head_status = self.dict_in_database(
            "dosing_head_status",
            {slot: DosingHeadStatus.normal.name for slot in self.ALL_SLOTS},
        )
        self.dosing_head_chemical = self.dict_in_database(
            "dosing_head_chemical",
            {slot: None for slot in self.ALL_SLOTS},
        )
        self.driver = None

    @mock(object_type=LabmanDosingHeadRack)
    def get_driver(self):
        """Get the driver for the dosing head rack."""
        return LabmanDosingHeadRack(self.firmware_version)

    def connect(self):
        """Connect to the dosing head rack."""
        self.driver = self.get_driver()
        self.driver.reference_search(timeout=120)

        for slot in self.ALL_SLOTS:
            status = self.get_dosing_head_status(slot)
            if status == DosingHeadStatus.in_use:
                self.request_maintenance(
                    f"Dosing head {slot} is in use. Please put the dosing head back in the rack.",
                    options=["OK"],
                )
                self.dosing_head_status[slot] = DosingHeadStatus.normal.name

    def disconnect(self):
        """Disconnect from the dosing head rack."""
        if self.driver is not None:
            self.driver.close()

    @property
    def sample_positions(self):
        """Get the sample positions."""
        return [
            SamplePosition(
                slot,
                description=f"The position of the dosing head rack at slot {slot}.",
            )
            for slot in self.ALL_SLOTS
        ]

    def move_to_slot(self, slot: int):
        """Move to a specific slot."""
        self.driver.move_to_slot(slot)

    def take_dosing_head(self, position: str):
        """Take the dosing head from a specific slot."""
        if self.get_dosing_head_status(position) != DosingHeadStatus.normal:
            raise ValueError(
                f"Dosing head {position} is not available. Current status: {self.get_dosing_head_status(position)}"
            )
        if self.get_dosing_head_chemical(position) is None:
            raise ValueError(f"Dosing head {position} is empty.")
        self.dosing_head_status[position] = DosingHeadStatus.in_use.name

    def return_dosing_head(self, position: str):
        """Return the dosing head to a specific slot."""
        if self.get_dosing_head_status(position) == DosingHeadStatus.in_use:
            self.dosing_head_status[position] = DosingHeadStatus.normal.name

    def update_dosing_head_status(
        self, dosing_head_position: str, status: DosingHeadStatus | str
    ):
        """Update the dosing head status."""
        if isinstance(status, str):
            status = DosingHeadStatus(status)
        self.dosing_head_status[dosing_head_position] = status.name

    def get_dosing_head_status(self, dosing_head_position: str) -> DosingHeadStatus:
        """Get the dosing head status."""
        return DosingHeadStatus(self.dosing_head_status[dosing_head_position])

    def get_dosing_head_chemical(self, dosing_head_position: str) -> str:
        """Get the dosing head chemical."""
        return self.dosing_head_chemical[dosing_head_position]

    def search_for_chemical(self, chemical: str) -> str | None:
        """Search for a chemical."""
        if chemical is None:
            raise ValueError("Chemical cannot be None.")
        for slot in self.ALL_SLOTS:
            if (
                self.get_dosing_head_chemical(slot) == chemical
                and self.get_dosing_head_status(slot) == DosingHeadStatus.normal
            ):
                return slot
        return None

    def set_dosing_head_chemical(self, dosing_head_position: str, chemical: str):
        """Set the dosing head chemical."""
        if self.get_dosing_head_chemical(dosing_head_position) is not None:
            raise ValueError(
                f"Dosing head {dosing_head_position} is already "
                f"occupied by {self.get_dosing_head_chemical(dosing_head_position)}."
            )
        self.dosing_head_chemical[dosing_head_position] = chemical
        self.dosing_head_status[dosing_head_position] = DosingHeadStatus.normal.name

    def remove_dosing_head_chemical(self, dosing_head_position: str):
        """Remove the dosing head chemical."""
        self.dosing_head_chemical[dosing_head_position] = None
        self.dosing_head_status[dosing_head_position] = DosingHeadStatus.normal.name

    def is_running(self):
        """Check if the dosing head rack is running."""
        return False
