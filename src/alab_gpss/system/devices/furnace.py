"""This module contains the GPSSBoxFurnace class for controlling the Eurotherm 3216p Box Furnace."""

import time
from traceback import format_exc
from typing import ClassVar

from alab_control.door_controller.door_controller_gpss import DoorController
from alab_control.furnace_3216p.furnace_driver import (
    FurnaceController,
)
from alab_control.furnace_3216p.furnace_driver import (
    SegmentFurnace3216P as Segment,
)
from alab_management.device_view import BaseDevice
from alab_management.device_view.device import log_signal, mock
from alab_management.sample_view import SamplePosition


class GPSSBoxFurnace(BaseDevice):
    """A device for controlling the Eurotherm 3216p Box Furnace."""

    description: ClassVar[str] = "Eurotherm 3216p Box Furnace"

    def __init__(
        self,
        com_port,
        door_controller_ip: str,
        furnace_letter: str,
        *args,
        **kwargs,
    ):
        """Initialize the GPSSBoxFurnace object."""
        super().__init__(*args, **kwargs)
        self.com_port = com_port
        self.driver = None
        self.door_controller = None
        self.door_controller_ip = door_controller_ip
        self.furnace_letter = furnace_letter

    @mock(object_type=[FurnaceController, DoorController])
    def get_driver(self):
        """Return the driver for the GPSSBoxFurnace."""
        self.driver = FurnaceController(port=self.com_port)
        self.door_controller = DoorController(
            ip_address=self.door_controller_ip,
        )
        return self.driver, self.door_controller

    def connect(self):
        """Connect to the GPSSBoxFurnace."""
        self.driver, self.door_controller = self.get_driver()

    def disconnect(self):
        """Disconnect from the GPSSBoxFurnace."""
        if self.driver is not None:
            self.driver.close()
        self.driver = None
        self.door_controller = None

    @property
    def sample_positions(self):
        """Return the sample positions of the GPSSBoxFurnace."""
        return [
            SamplePosition(
                "crucible",
                description="The crucible position inside the box furnace, where the crucible should sit on"
                "top of the furnace rack",
                number=8,
            ),
            SamplePosition(
                "furnace_rack",
                description="The position inside the box furnace, where the furnace rack is located",
            ),
            SamplePosition(
                "cooling_area/furnace_rack",
                description="The position inside the cooling area, where the furnace rack is located",
            ),
            SamplePosition(
                "cooling_area/crucible",
                description="The position inside the cooling area, where the crucible is located",
                number=8,
            ),
        ]

    def emergent_stop(self):
        """Stop the GPSSBoxFurnace."""
        self.driver.stop()

    def run_program(
        self,
        profiles: list[list] = None,
    ):
        """
        Default template is used by filling in only heating_time_minutes and heating_temperature profiles is a list of
        [temperature, rate, dwelling time in minutes]. For example: [[1000, 5, 60], [1200, 5, 240]].
        """
        segments = []
        for profile in profiles:
            if profile[2] > 900:
                segments.extend(
                    [
                        Segment(
                            target_temperature=profile[0],
                            ramp_rate=profile[1],
                            dwell_time_min=900,
                        ),
                    ]
                    * (profile[2] // 900)
                    + [
                        Segment(
                            target_temperature=profile[0],
                            ramp_rate=profile[1],
                            dwell_time_min=profile[2] % 900,
                        ),
                    ]
                )
            else:
                segments.append(
                    Segment(
                        target_temperature=profile[0],
                        ramp_rate=profile[1],
                        dwell_time_min=profile[2],
                    )
                )
        self.set_message(
            f"Run the following segments:\n"
            f"{'; '.join(f'({i}) {segment.target_temperature} C, {segment.ramp_rate} C/min, {segment.dwell_time_min} min' for i, segment in enumerate(segments, 1))}"
        )

        self.driver.run_program(*segments)
        time.sleep(2)

    @mock(return_constant=False)
    def is_running(self) -> bool:
        """
        Returns True if the box furnace is either:
            - currently running a program
            - too hot to be opened (ie still cooling down from a recently completed program).
        """
        return self.driver.is_running()

    @mock(return_constant=30)
    @log_signal("temperature", interval_seconds=60)
    def get_temperature(self) -> float:
        """Return the current temperature of the GPSSBoxFurnace."""
        return self.driver.current_temperature

    def open_door(self):
        """Open the door of the GPSSBoxFurnace."""
        while True:
            try:
                self.door_controller.open_furnace(name=self.furnace_letter, block=True)
                break
            except:
                response = self.request_maintenance(
                    f"Failed to open the furnace door {self.furnace_letter}. "
                    f"The error message is {format_exc()}",
                    options=["Retry", "Cancel"],
                )

                if response == "Cancel":
                    raise

    def close_door(self):
        """Close the door of the GPSSBoxFurnace."""
        while True:
            try:
                self.door_controller.close_furnace(name=self.furnace_letter, block=True)
                break
            except:
                response = self.request_maintenance(
                    f"Failed to close the furnace door {self.furnace_letter}. "
                    f"The error message is {format_exc()}",
                    options=["Retry", "Cancel"],
                )

                if response == "Cancel":
                    raise
