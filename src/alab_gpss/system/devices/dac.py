from __future__ import annotations

from typing import ClassVar

from alab_control.speedmixer_hauschild_smart_dac400.dac import (
    DACError,
)
from alab_control.speedmixer_hauschild_smart_dac400.dac import (
    HauschildDAC400 as DACDriver,
)
from alab_management.device_view import BaseDevice
from alab_management.device_view.device import mock
from alab_management.sample_view import SamplePosition


class DAC(BaseDevice):
    """A device for controlling a DAC."""

    description: ClassVar[str] = "DAC for mixing powders"

    def __init__(self, com_port: str, *args, **kwargs):
        """Initialize the DAC object."""
        super().__init__(*args, **kwargs)
        self.com_port = com_port
        self.driver: DACDriver | None = None

    @mock(object_type=DACDriver)
    def get_driver(self):
        """Return the driver for the DAC."""
        self.driver = DACDriver(com_port=self.com_port)
        return self.driver

    def connect(self):
        """Connect to the DAC."""
        self.driver = self.get_driver()

    def disconnect(self):
        """Disconnect from the DAC."""
        if self.driver is not None:
            self.driver.stop()
            self.driver = None

    @property
    def sample_positions(self):
        """Return the sample positions of the DAC."""
        return [
            SamplePosition(
                "crucible",
                description="The mixing holder for the DAC",
            ),
            SamplePosition(
                "dac_lid",
                description="The position to put the DAC lid on",
            ),
        ]

    def emergent_stop(self):
        """Stop the DAC."""
        if self.driver:
            self.driver.stop()

    def stop(self):
        """Stop the DAC."""
        self.driver.stop()

    def mixing(self, speed: int, time_sec: int):
        """Mix the powders."""
        if not 100 <= speed <= 2000:
            raise ValueError("Speed must be between 100 and 2000")
        if not 10 <= time_sec <= 60 * 10:
            raise ValueError("Time must be between 10 and 600 seconds")
        self.set_message(f"DAC is running for speed: {speed} RPM, time: {time_sec} sec")
        while True:
            try:
                self.driver.run_program(speed, time_sec)
            except DACError as e:
                try:
                    self.driver.stop()
                except DACError:
                    failed_stop = True
                else:
                    failed_stop = False
                response = self.request_maintenance(
                    prompt=f"Error during running the DAC{' (failed to stop)' if failed_stop else ''}: {e}",
                    options=["Retry", "Cancel"],
                )
                if response == "Cancel":
                    raise
            else:
                break

    def homing(self):
        """Homing the DAC."""
        self.set_message("Setting the DAC to home position.")
        while True:
            try:
                self.driver.homing()
            except DACError as e:
                self.driver.stop()
                response = self.request_maintenance(
                    prompt=f"Error during homing the DAC: {e}",
                    options=["Retry", "Cancel"],
                )
                if response == "Cancel":
                    raise
            else:
                break
        self.set_message("")

    def is_running(self) -> bool:
        """Return whether the DAC is running."""
        return self.driver.is_running()
