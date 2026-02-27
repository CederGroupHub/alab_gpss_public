import time
from threading import Thread
from traceback import print_exc
from typing import Literal
from xmlrpc.server import SimpleXMLRPCServer

from alab_control.dh_robotic_gripper.dh_robotic_gripper import (
    GripperController,
    RotationMode,
)
from alab_management import mock
from alab_management.device_view import BaseDevice
from alab_management.sample_view import SamplePosition
from alab_management.user_input import request_user_input


class CapperXMLRPC:
    def __init__(self, capper_address):
        self.capper_address = capper_address
        self.gripper = self.get_gripper()
        self.gripper.initialize()

    @mock(object_type=GripperController)
    def get_gripper(self):
        self.gripper = GripperController(port=self.capper_address)
        return self.gripper

    def __del__(self):
        """Ensure the gripper connection is closed when the object is deleted."""
        try:
            self.gripper.close()
        except Exception:
            print_exc()

    def open(self):
        try:
            self.gripper.open_to(position=500)
            return True
        except Exception:
            print_exc()
            return False

    @mock(return_constant=True)
    def zero_position(self):
        try:
            current_angle = self.gripper.read_current_angle()
            self.gripper.rotate(
                deg=335 - current_angle % 180,  # Adjusting to zero position
                speed=50,
                check_gripper=False,
                mode=RotationMode.RELATIVE,
            )
            return True
        except Exception:
            print_exc()
            return False

    def open_fully(self):
        try:
            self.gripper.open_to(position=1000)
            return True
        except Exception:
            print_exc()
            return False

    def close(self):
        try:
            self.gripper.grasp(speed_percentage=40)
            self.gripper.open_to(position=1000)
            self.gripper.grasp(speed_percentage=20)
            return True
        except Exception:
            print_exc()
            return False

    def ping(self):
        return "pong"

    def cap(self):
        try:
            self.gripper.set_rotating_blocking(True)
            self.gripper.set_gripper_force(90)
            self.gripper.set_rotation_speed(15)
            self.gripper.set_rotation_force(50)
            self.gripper.set_rotation_angle(-360 * 20)
            return True
        except Exception:
            print_exc()
            return False

    def decap(self):
        try:
            self.gripper.set_rotating_blocking(False)
            self.gripper.set_gripper_force(100)
            self.gripper.set_rotation_speed(20)
            self.gripper.set_rotation_force(100)
            self.gripper.set_rotation_angle(360 * 5)
            return True
        except Exception:
            print_exc()
            return False

    def stop(self):
        try:
            self.gripper.stop_rotation()
            return True
        except Exception:
            print_exc()
            return False

    def status(self) -> Literal["MOVING", "REACHED", "BLOCKED", "BLOCKED_MOVING", ""]:
        try:
            return self.gripper.read_rotation_status().name
        except Exception:
            print_exc()
            return ""


class XMLRPCServerWithStopping(SimpleXMLRPCServer):
    timeout = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def stop(self):
        self.shutdown()


class VialCapper(BaseDevice):
    description = """A device for the vial capper. 
    It is used for applying and removing cap from the vial"""

    def __init__(self, com_port, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.com_port = com_port
        self.connected = False
        self.xmlrpc_server_thread = None
        self.xmlrpc_server = None
        self.capper_driver = None
        self.gripper_client = None

    def get_xmlrpc_server(self):
        """Start the XML-RPC server."""
        self.gripper_client = CapperXMLRPC(capper_address=self.com_port)
        server = XMLRPCServerWithStopping(("", 8872), allow_none=True)
        server.register_introspection_functions()
        server.register_instance(self.gripper_client)
        return server

    def connect(self):
        self.connected = True
        self.xmlrpc_server = self.get_xmlrpc_server()
        self.xmlrpc_server_thread = Thread(
            target=self.xmlrpc_server.serve_forever, daemon=True
        )
        self.xmlrpc_server_thread.start()
        time.sleep(1)

    def disconnect(self):
        if self.xmlrpc_server is not None:
            self.xmlrpc_server.stop()
            self.xmlrpc_server_thread.join()
            self.xmlrpc_server.server_close()
            self.xmlrpc_server = None
            self.xmlrpc_server_thread = None
        self.connected = False

    def error_handling(self, func, *args, **kwargs):
        """A wrapper for error handling when calling driver methods."""
        automatic_retry = 0
        while True:
            result = func(*args, **kwargs)
            if not result:
                if automatic_retry < 2:
                    automatic_retry += 1
                    continue
                else:
                    automatic_retry = 0
                    response = request_user_input(
                        task_id=None,
                        prompt=f"Error executing the operation on {self.name}",
                        options=["Retry", "Cancel"],
                        maintenance=True,
                    )
                    if response == "Cancel":
                        raise RuntimeError("Operation cancelled by user.")
                self.disconnect()
                time.sleep(5)
                self.connect()
            else:
                return result

    def open_fully(self):
        """Open the gripper fully."""
        if not self.connected:
            raise RuntimeError("Device not connected.")
        self.error_handling(lambda: self.gripper_client.open_fully())

    def open(self):
        """Open the gripper."""
        if not self.connected:
            raise RuntimeError("Device not connected.")

        self.error_handling(
            lambda: self.gripper_client.open(),
        )

    def close(self):
        """Close the gripper."""
        if not self.connected:
            raise RuntimeError("Device not connected.")

        self.error_handling(lambda: self.gripper_client.close())

    def zero_position(self):
        """Set the gripper to zero position."""
        if not self.connected:
            raise RuntimeError("Device not connected.")

        self.error_handling(lambda: self.gripper_client.zero_position())

    def stop(self):
        """Stop the gripper."""
        if not self.connected:
            raise RuntimeError("Device not connected.")

        self.gripper_client.stop()

    @property
    def sample_positions(self):
        return [
            SamplePosition(
                "vial",
                description="The position of the vial capper.",
            )
        ]

    def is_running(self):
        return False
