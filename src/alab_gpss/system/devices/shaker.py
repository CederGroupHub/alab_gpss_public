"""This module contains the Shaker class for controlling a vertical shaker."""

from __future__ import annotations

from traceback import print_exc
from typing import Callable, ClassVar

from alab_control.dh_linear_rail.dh_linear_rail_mce_3g import LinearRailController3G
from alab_control.shaker_with_motor_controller.shaker_with_motor_controller import (
    ShakerWMC as ShakerDriver,
)
from alab_management.device_view import BaseDevice
from alab_management.device_view.device import mock
from alab_management.sample_view import SamplePosition


class Shaker(BaseDevice):
    """A device for controlling a vertical shaker."""

    description: ClassVar[str] = (
        "Vertical shaker for grinding powders in a crucible or plastic vial."
    )

    def __init__(
        self,
        linear_rail_com_port: str,
        ip_address: str,
        port: int = 80,
        *args,
        **kwargs,
    ):
        """Initialize the Shaker object."""
        super().__init__(*args, **kwargs)
        self.ip_address = ip_address
        self.port = port
        self.linear_rail_com_port = linear_rail_com_port
        self.driver: ShakerDriver | None = None
        self.linear_rail_driver: LinearRailController3G | None = None

    @mock(object_type=[ShakerDriver, LinearRailController3G])
    def get_driver(self):
        """Return the driver for the Shaker."""
        self.driver = ShakerDriver(ip_address=self.ip_address, port=self.port)
        self.linear_rail_driver = LinearRailController3G(port=self.linear_rail_com_port)
        return self.driver, self.linear_rail_driver

    def connect(self):
        """Connect to the Shaker."""
        self.driver, self.linear_rail_driver = self.get_driver()
        self.linear_rail_driver.initialize()

    def disconnect(self):
        """Disconnect from the Shaker."""
        if self.driver is not None:
            self.driver.stop()
            self.linear_rail_driver.close()
        self.driver = None
        self.linear_rail_driver = None

    @property
    def sample_positions(self):
        """Return the sample positions of the Shaker."""
        return [
            SamplePosition(
                "crucible",
                description="Slot that can accept one sample (in either a crucible or plastic vial)",
            ),
            SamplePosition(
                "vial",
                description="Slot that can accept one sample (in either a crucible or plastic vial)",
            ),
            SamplePosition(
                "dumping/crucible",
                description="Slot that is used for dumping powder from crucible to a vial",
            ),
        ]

    def emergent_stop(self):
        """Stop the Shaker."""
        if self.driver:
            self.driver.stop()

    def shake(
        self, duration_seconds: float, frequency_hz: int, close_gripper: bool = True
    ):
        """Closes the vertical shaker to grab the sample, shakes it for the duration, then releases the shaker.

        Args:
             duration_seconds (float): seconds to shake
             close_gripper (bool): whether to clamp (True) or not (False). Defaults to True.
             frequency_hz (int): frequency of the shaker in Hz
        """
        if self.driver is None:
            raise ValueError("Driver not set. Cannot perform shake operation.")

        self.set_message(f"Shaking for {duration_seconds} seconds at {frequency_hz} Hz")

        if close_gripper:
            self.close_gripper()  # this is blocking
        self.driver.shaking(
            duration_sec=duration_seconds, frequency=frequency_hz
        )  # this is blocking

        self.set_message("")

    @mock(return_constant=False)
    def is_running(self) -> bool:
        """Return whether the Shaker is running."""
        if self.driver:
            return self.driver.is_running()

        raise Exception("Cannot check if shaker is running, not connected")

    def handle_error(self, func: Callable):
        while True:
            try:
                func()
                break
            except Exception as e:
                response = self.request_maintenance(
                    prompt=f"Error during gripper operation: {e}",
                    options=["Retry", "Cancel"],
                )
                if response == "Cancel":
                    raise

    def close_gripper(self):
        """Close the gripper to hold the container."""
        self.handle_error(self.driver.close_gripper)

    def open_gripper(self):
        """Open the gripper to release the container."""
        self.handle_error(self.driver.open_gripper)

    def reset(self):
        """Reset the Shaker."""
        self.driver.reset()

    def handle_rail_error(self, func: Callable):
        automatic_retry = 0
        while True:
            try:
                return func()
            except Exception as e:
                print_exc()
                self.disconnect()
                self.connect()
                if automatic_retry < 2:
                    automatic_retry += 1
                    continue
                automatic_retry = 0
                response = self.request_maintenance(
                    prompt=f"Error during rail operation: {e}",
                    options=["Retry", "Cancel"],
                )
                if response == "Cancel":
                    raise

    def move_rail_to_loading_position(self):
        """Move the rail to the loading position."""
        self.handle_rail_error(lambda: self.linear_rail_driver.move_to(position=50))

    def move_rail_to_dumping_position(self):
        """Move the rail to the dumping position."""
        self.handle_rail_error(lambda: self.linear_rail_driver.move_to(position=8))
