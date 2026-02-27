from __future__ import annotations

import time
from traceback import print_exc

from alab_control.xrd_dispenser.xrd_dispenser import (
    XRDDispenserResult,
    XRDPrepController,
)
from alab_management.device_view import BaseDevice
from alab_management.device_view.device import mock
from alab_management.sample_view import SamplePosition
from alab_management.user_input import request_user_input


class XRDDispenser(BaseDevice):
    description = """A device for the XRD dispenser. It is used for transferring samples to the XRD."""

    def __init__(
        self,
        gripper_port,
        rail_port,
        balance_ip,
        shaker_ip,
        shaker_com_port,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.gripper_port = gripper_port
        self.rail_port = rail_port
        self.balance_ip = balance_ip
        self.shaker_ip = shaker_ip
        self.shaker_com_port = shaker_com_port
        self.driver: XRDPrepController | None = None
        self.running = False

    @mock(object_type=XRDPrepController)
    def get_driver(self):
        self.driver = XRDPrepController(
            gripper_port=self.gripper_port,
            rail_port=self.rail_port,
            balance_ip=self.balance_ip,
            shaker_ip=self.shaker_ip,
            shaker_com_port=self.shaker_com_port,
        )
        return self.driver

    def connect(self):
        self.driver = self.get_driver()
        self.driver.initialize()

    def disconnect(self):
        if self.driver is not None:
            self.driver.close()
            self.driver = None

    def move_to_loading_position(self):
        automatic_retries = 0
        while True:
            try:
                self.set_message("Moving to loading position...")
                self.driver.move_rail_backward()
                self.driver.open_gripper()
                self.set_message("")
                return
            except Exception as e:
                print_exc()
                self.disconnect()
                time.sleep(1)
                self.connect()

                if automatic_retries < 2:
                    automatic_retries += 1
                    continue
                automatic_retries = 0
                response = request_user_input(
                    task_id=None,
                    prompt=f"Error moving to loading position: {e}",
                    options=["Retry", "Cancel"],
                    maintenance=True,
                )
                if response == "Cancel":
                    raise

    @mock(
        return_constant=XRDDispenserResult(
            initial_mass=0.0,
            final_mass=0.0,
            target_mass=0.0,
            mass_reached=True,
            dispensed_mass=0.0,
        )
    )
    def dispensing_powder(
        self,
        target_mass,
        tolerance: int = 10,
        angle_offset: int = 5,
    ) -> XRDDispenserResult:
        while True:
            try:
                self.running = True
                self.set_message("Dispensing powder...")
                result = self.driver.dispensing_powder(
                    target_mass, tolerance, angle_offset
                )
                self.set_message("")
                self.running = False
                return result
            except Exception as e:
                print_exc()
                self.disconnect()
                time.sleep(1)
                self.connect()
                try:
                    self.driver.homing()
                except:
                    print_exc()

                self.running = False
                response = request_user_input(
                    task_id=None,
                    prompt=f"Error dispensing powder: {e}",
                    options=["Retry", "Cancel"],
                    maintenance=True,
                )
                if response == "Cancel":
                    raise

    @property
    def sample_positions(self):
        return [
            SamplePosition(
                name="xrd_sample_holder",
                description="The XRD sample holder on the balance to receive the powder",
            ),
            SamplePosition(
                name="vial",
                description="The vial on the rail to dispense the powder",
            ),
        ]

    def is_running(self):
        return self.running
