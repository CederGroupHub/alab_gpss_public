from __future__ import annotations

import time
from abc import ABC

from alab_control.robot_arm_ur5e.robots import BaseURRobot
from alab_control.robot_arm_ur5e.ur_robot_dashboard import URRobotError
from alab_management.device_view import BaseDevice
from alab_management.device_view.device import mock
from alab_management.sample_view import SamplePosition
from alab_management.user_input import request_user_input


class _BaseGPSSRobotArm(BaseDevice, ABC):
    """A device for UR5e robot arm in the GPSS system."""

    description: str = "UR5e robot arm in the GPSS system"

    def __init__(self, ip: str, *args, **kwargs):
        """Initialize the BaseGPSSRobotArm object."""
        super().__init__(*args, **kwargs)
        self.ip = ip
        self.driver: BaseURRobot | None = None

    @mock(object_type=BaseURRobot)
    def get_driver(self):
        """Return the driver for the BaseGPSSRobotArm."""
        self.driver = BaseURRobot(self.ip)
        self._confirm_connection_in_remote_mode()
        return self.driver

    def connect(self):
        """Connect to the BaseGPSSRobotArm."""
        self.driver = self.get_driver()

    def disconnect(self):
        """Disconnect from the BaseGPSSRobotArm."""
        if self.driver is not None:
            self.driver.close()

    def _confirm_connection_in_remote_mode(self):
        if self.driver is None:
            raise Exception("Device is not connected!")
        while not self.driver.is_remote_mode():
            self._device_view.pause_device(self.name)
            self.set_message(
                "The arm is not under remote control. Please set to remote control and try again."
            )
            self.request_maintenance(
                prompt=f"Please set {self.name} to remote control, then press OK to continue.",
                options=["OK"],
            )
            if self.driver.is_remote_mode():
                self._device_view.unpause_device(self.name)
                self.set_message(
                    f"Successfully connected to {self.name} in remote control mode!"
                )

    def wait_for_finish(self):
        """Wait for the robot arm to finish."""
        while self.is_running():
            time.sleep(0.2)

    def run_programs(self, programs):
        """Run multiple programs on the robot arm."""
        for p in programs:
            self.run_program(p, block=True, user_input_recovery=True)

    def is_running(self):
        """Return whether the BaseGPSSRobotArm is running."""
        while True:
            try:
                return self.driver.is_running()
            except (ConnectionError, URRobotError):
                response = request_user_input(
                    task_id=None,
                    prompt="Set the robot arm to remote mode and try again.",
                    options=["Retry", "Cancel"],
                    maintenance=True,
                )
                if response == "Cancel":
                    raise
                self.disconnect()
                self.connect()

    def run_program(
        self, program, block: bool = True, user_input_recovery: bool = True
    ):
        """Run a program on the robot arm."""
        # check if the robot arm can be connected
        self.is_running()

        while True:
            try:
                self.set_message(f"Running program: {program}")
                self.driver.run_program(program, block=block)
                self.set_message("")
            except URRobotError as exc:
                if user_input_recovery:
                    response = request_user_input(
                        task_id=None,
                        prompt=f"Exception from {self.name}: {exc.args[0]}"
                        f"Set the robot arm to the starting position of {program} and try again.",
                        options=["Retry", "Skip", "Cancel"],
                        maintenance=True,
                    )
                    if response == "Cancel":
                        raise
                    if response == "Skip":
                        self.set_message("")
                        break
                    if "reconnect to port 29999" in exc.args[0]:
                        self.disconnect()
                        self.connect()
                else:
                    raise exc
            except (OSError, ConnectionError):
                # This is a workaround for the issue where the robot arm disconnects and somehow the connection hangs
                response = request_user_input(
                    task_id=None,
                    prompt=f"Set the robot arm to the starting position of {program} and try again.",
                    options=["Retry", "Skip", "Cancel"],
                    maintenance=True,
                )
                if response == "Cancel":
                    raise
                if response == "Skip":
                    self.set_message("")
                    break
                self.disconnect()
                self.connect()
            except Exception as exc:
                response = request_user_input(
                    task_id=None,
                    prompt=f"Exception from {self.name}: {exc.args[0]}"
                    f"Set the robot arm to the starting position of {program} and try again.",
                    options=["Retry", "Skip", "Cancel"],
                    maintenance=True,
                )
                if response == "Cancel":
                    raise
                if response == "Skip":
                    self.set_message("")
                    break
                if "reconnect to port 29999" in exc.args[0]:
                    self.disconnect()
                    self.connect()
            else:
                break


class GPSSRobotArmFurnace(_BaseGPSSRobotArm):
    """A device for UR5e robot arm in the furnace side of the GPSS system."""

    description: str = "UR5e robot arm in the furnace side of the GPSS system"

    def open_consumble_rack(self, level: int):
        """Open the consumble rack at the given level."""
        if not 1 <= level <= 7:
            raise ValueError(f"Invalid level: {level}")
        self.run_program(
            f"auto_program/open_consumable_rack/open_level_{level}.auto.urp"
        )

    def close_consumble_rack(self, level: int):
        """Close the consumble rack at the given level."""
        if not 1 <= level <= 7:
            raise ValueError(f"Invalid level: {level}")
        self.run_program(
            f"auto_program/close_consumable_rack/close_level_{level}.auto.urp"
        )

    def read_installation_variable(self, name: str, default_value=None):
        installation_variables = self.driver.ssh.read_installation_variables()
        return installation_variables.get(name, default_value)

    @mock(return_constant=False)
    def pick_crucible_from_dac(self):
        """Pick the crucible from the DAC."""
        self.run_program("auto_program/pick_cru_dac.auto.urp")
        return self.read_installation_variable("cru_picked").strip('"') == "true"

    @mock(return_constant=False)
    def pick_crucible_from_capper(self):
        """Pick the crucible from the capper."""
        self.run_program("auto_program/pick_cru_capper.auto.urp")
        self.run_program("auto_program/check_crucible_picked.auto.urp")
        return self.read_installation_variable("cru_picked").strip('"') == "true"

    @mock(return_constant=False)
    def pick_crucible_from_crucible_holder(self):
        """Pick the crucible from the crucible holder."""
        self.run_program("auto_program/pick_crucible_near_bdis.auto.urp")
        self.run_program("auto_program/check_crucible_picked.auto.urp")
        return self.read_installation_variable("cru_picked").strip('"') == "true"

    @mock(return_constant=True)
    def check_crucible_picked(self):
        """Check if the crucible is picked."""
        self.run_program("auto_program/check_crucible_picked.auto.urp")
        return self.read_installation_variable("cru_picked").strip('"') == "true"

    def capping_crucible_on_crucible_holder(self):
        """Capping the crucible on the crucible holder."""
        self.run_program(
            "auto_program/place_crucible_near_bdis.auto.urp"
        )  # this program works for dropping cap.

    def capping_crucible(self):
        """Capping the crucible with the hole plug"""
        self.run_program("auto_program/capping.auto.urp")

    def decapping_crucible(self):
        """Decapping the crucible with the hole plug"""
        self.run_program("auto_program/decapping.auto.urp")

    def dumping_balls(self):
        """Dumping balls from the crucible."""
        self.run_program("auto_program/dumping_balls.auto.urp")

    def dispose_hole_plug(self):
        """Dispose the hole plug"""
        self.run_program("auto_program/dispose_hole_plug.auto.urp")

    @property
    def sample_positions(self):
        """Return the sample positions of the robot arm."""
        return [
            SamplePosition(
                "gripper_v",
                description="The position of robot arm gripping containers vertically.",
            ),
            SamplePosition(
                "gripper_hf",
                description="The position of robot arm gripping furnace racks horizontally.",
            ),
            SamplePosition(
                "gripper_hdac",
                description="The position of robot arm gripping containers horizontally (near DAC).",
            ),
        ]


class GPSSRobotArmPowder(_BaseGPSSRobotArm):
    """A device for UR5e robot arm in the powder side of the GPSS system."""

    description: str = "UR5e robot arm in the powder side of the GPSS system"

    def capping_vial(self):
        """Capping the vial with the cap"""
        self.run_program("check_capper_connect.urp")
        self.run_program("auto_program/capping.auto.urp")

    def decapping_vial(self):
        """Decapping the vial with the cap"""
        self.run_program("check_capper_connect.urp")
        self.run_program("auto_program/decapping.auto.urp")

    def disposing_dirty_caps(self):
        """Dispose the dirty caps"""
        self.run_program("auto_program/dispose.auto.urp")

    def shaking_dosing_head(self):
        """Shake the dosing head"""
        self.run_program("auto_program/shaking_dosing_head.auto.urp")

    @property
    def sample_positions(self):
        """Return the sample positions of the robot arm."""
        return [
            SamplePosition(
                "gripper_dosing_head",
                description="The position of robot arm gripping the dosing head.",
            ),
            SamplePosition(
                "gripper_v",
                description="The position of robot arm gripping the containers.",
            ),
        ]
