import time
from traceback import print_exc

from alab_control.dh_robotic_gripper.dh_robotic_gripper import GripperController
from alab_management.device_view import BaseDevice
from alab_management.device_view.device import mock
from alab_management.sample_view import SamplePosition
from alab_management.user_input import request_user_input


class CrucibleCapper(BaseDevice):
    description = """A device for the crucible capper. 
    It is used for applying and removing hole plug from the crucible"""

    def __init__(self, com_port, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.com_port = com_port
        self.driver = None

    @mock(object_type=GripperController)
    def get_driver(self):
        self.driver = GripperController(port=self.com_port)
        return self.driver

    def connect(self):
        self.driver = self.get_driver()
        self.driver.initialize()

    def disconnect(self):
        if self.driver is not None:
            try:
                self.driver.close()
            except:  # noqa: E722
                pass
            self.driver = None

    def error_handling(self, func, *args, **kwargs):
        """A wrapper for error handling when calling driver methods."""
        automatic_retry = 0
        while True:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print_exc()
                self.disconnect()
                self.connect()
                if automatic_retry < 2:
                    automatic_retry += 1
                    continue
                automatic_retry = 0
                response = request_user_input(
                    task_id=None,
                    prompt=f"Error executing the operation on {self.name}: {e}",
                    options=["Retry", "Cancel"],
                    maintenance=True,
                )
                if response == "Cancel":
                    raise

    def open_to(self, position: int):
        """Open the capper to a specific position. With error handling."""
        self.error_handling(
            lambda: self.driver.open_to(position=position),
        )

    def open(self):
        self.open_fully()
        time.sleep(0.5)
        self.open_to(position=650)

    def open_fully(self):
        self.open_to(position=1000)

    def close(self):
        self.open_fully()
        time.sleep(0.5)
        self.driver.grasp()

    def calibrate(self):
        self.close()
        self.open()

    @mock(return_constant=1000)
    def get_position(self):
        """Get the current position of the capper."""
        return self.error_handling(lambda: self.driver.read_gripper_position())

    @property
    def sample_positions(self):
        return [
            SamplePosition(
                "crucible",
                description="The position of the crucible capper.",
            )
        ]

    def is_running(self):
        return False
