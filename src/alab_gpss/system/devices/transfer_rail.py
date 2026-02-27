from __future__ import annotations

from typing import Callable

from alab_control.linear_rail_gpss.linear_rail_gpss import LinearRailGPSS
from alab_management.device_view import BaseDevice
from alab_management.device_view.device import mock
from alab_management.sample_view import SamplePosition
from alab_management.user_input import request_user_input


def handle_error(func: Callable):
    """Handle errors from the transfer rail."""
    while True:
        try:
            return func()
        except Exception as e:
            response = request_user_input(
                task_id=None,
                prompt=f"Error moving the transfer rail: {e}",
                options=["Retry", "Cancel"],
                maintenance=True,
            )
            if response == "Cancel":
                raise


class TransferRail(BaseDevice):
    """A device for the transfer rail."""

    description: str = (
        "Transfer rail that moves containers between the furnace and the powder side."
    )

    def __init__(self, firmware_version: int, *args, **kwargs):
        """Initialize the transfer rail."""
        super().__init__(*args, **kwargs)
        self.firmware_version = firmware_version
        self.driver: LinearRailGPSS | None = None

    @mock(object_type=LinearRailGPSS)
    def get_driver(self):
        """Get the driver for the transfer rail."""
        self.driver = LinearRailGPSS(self.firmware_version)
        return self.driver

    def connect(self):
        """Connect to the transfer rail."""
        self.driver = self.get_driver()

    def disconnect(self):
        """Disconnect from the transfer rail."""
        if self.driver is not None:
            self.driver.close()

    @mock(return_constant=None)
    def move_to_furnace_side(self):
        """Move the transfer rail to the left."""
        self.set_message("Moving transfer rail to the left.")
        handle_error(self.driver.move_left)
        self.set_message("")

    @mock(return_constant=None)
    def move_to_powder_side(self):
        """Move the transfer rail to the right."""
        self.set_message("Moving transfer rail to the right.")
        handle_error(self.driver.move_right)
        self.set_message("")

    @property
    def sample_positions(self):
        """Return the sample positions of the transfer rail."""
        all_positions = []
        for pos in ["left", "right"]:
            for consumable in ["cap", "cap_sieved", "crucible", "vial"]:
                all_positions.append(
                    SamplePosition(
                        f"{pos}/{consumable}",
                        description=f"The position of the transfer rail on the {pos} with {consumable}.",
                    )
                )
        return all_positions

    def is_running(self) -> bool:
        return self.driver.is_running()
