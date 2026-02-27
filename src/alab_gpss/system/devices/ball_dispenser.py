"""This module contains the BallDispenser class for dispensing milling balls into
crucibles or plastic vials for grinding powders.
"""

from __future__ import annotations

from typing import ClassVar

from alab_control.ball_dispenser import BallDispenser as BallDispenserDriver
from alab_control.ball_dispenser import EmptyError
from alab_management.device_view import BaseDevice
from alab_management.device_view.device import mock
from alab_management.sample_view import SamplePosition


class BallDispenser(BaseDevice):
    """A device for dispensing milling balls into crucibles or plastic vials for grinding powders."""

    description: ClassVar[str] = (
        "Dispenses milling balls into crucibles or plastic vials for grinding powders."
    )

    def __init__(self, ip_address: str, port: int = 80, *args, **kwargs):
        """Initialize the BallDispenser object."""
        super().__init__(*args, **kwargs)
        # self._stock = initial_fill
        self.ip_address = ip_address
        self.port = port
        self.driver: BallDispenserDriver | None = None

    @mock(object_type=BallDispenserDriver)
    def get_driver(self):
        """Return the driver for the BallDispenser."""
        self.driver = BallDispenserDriver(ip_address=self.ip_address, port=self.port)
        return self.driver

    def connect(self):
        """Connect to the BallDispenser."""
        self.driver = self.get_driver()

    def disconnect(self):
        """Disconnect from the BallDispenser."""
        self.driver = None

    @property
    def sample_positions(self):
        """Return the sample positions of the BallDispenser."""
        return [
            SamplePosition(
                "crucible",
                description="A slot for either a crucible or vial. Sample is placed here during dispensing.",
            )
        ]

    def dispense_many(self, num: int):
        """
        Dispense multiple balls.

        Args:
            num: The number of balls to dispense.

        Returns:
            Error: Whether an EmptyError occurred.
            dispensed_amount: The total number of balls dispensed.
        """
        # in the current ball dispenser, the number of balls dispensed will always be doubled due to the hardware issue
        num = num // 2
        for _ in range(num):
            self.dispense_one()

    def dispense_one(self):
        """Dispense a single ball."""
        self.set_message("Dispensing one ball...")
        self.driver.change_number(1)  # set the number of balls to dispense to 1
        while True:
            try:
                self.driver.dispense_balls()  # this dispenses a single ball
                break
            except EmptyError:
                self.request_refill()
        self.set_message("")

    def request_refill(self):
        """Request a refill of milling balls."""
        self.set_message("Out of balls! Submitted maintenance request for refill.")
        reply = "Unsuccessful"
        while reply == "Unsuccessful":
            reply = self.request_maintenance(
                prompt=f"{self.name} is empty. Reload with milling balls.",
                options=["Success", "Unsuccessful"],
            )
        self.set_message("")

    def is_running(self):
        """Return whether the BallDispenser is running."""
        return self.driver.get_state().value == "RUNNING"
