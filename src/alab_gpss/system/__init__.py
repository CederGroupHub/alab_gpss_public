from alab_management import (
    SamplePosition,
    add_device,
    add_standalone_sample_position,
    add_task,
)
from alab_management.config import AlabOSConfig
from serial.tools import list_ports

from alab_gpss.system.devices.auto_balance import AutoBalance
from alab_gpss.system.devices.ball_dispenser import BallDispenser
from alab_gpss.system.devices.consumable_rack import ConsumableRack
from alab_gpss.system.devices.crucible_capper import CrucibleCapper
from alab_gpss.system.devices.dac import DAC
from alab_gpss.system.devices.dosing_head_rack import DosingHeadRack
from alab_gpss.system.devices.furnace import GPSSBoxFurnace
from alab_gpss.system.devices.label_printer import LabelPrinter
from alab_gpss.system.devices.robot_arm import GPSSRobotArmFurnace, GPSSRobotArmPowder
from alab_gpss.system.devices.shaker import Shaker
from alab_gpss.system.devices.transfer_rail import TransferRail
from alab_gpss.system.devices.vial_capper import VialCapper
from alab_gpss.system.devices.xrd_dispenser import XRDDispenser
from alab_gpss.system.devices.xrd_sample_holder_rack import XRDSampleHolderRack
from alab_gpss.system.tasks.add_sample import GPSSAddSample
from alab_gpss.system.tasks.heating import GPSSHeating
from alab_gpss.system.tasks.moving import GPSSMoving
from alab_gpss.system.tasks.powder_dispensing import GPSSPowderDispensing
from alab_gpss.system.tasks.powder_mixing import GPSSPowderMixing
from alab_gpss.system.tasks.remove_sample import RemoveSample
from alab_gpss.system.tasks.sample_grinding_xrd import GPSSSampleGrindingXRD

ethernet_devices_ips = {
    "gpss/auto_balance": "192.168.1.91",
    "gpss/balance_restarter": "192.168.1.78",
    "gpss/ball_dispenser": "192.168.1.235",
    "gpss/door_opener": "192.168.1.88",
    "gpss/xrd_dispenser_balance": "192.168.1.62",
    "gpss/shaker_gripper": "192.168.1.191",
    "gpss/xrd_dispenser_vibrational_motor": "192.168.1.58",
    "gpss/powder_robot": "192.168.1.205",
    "gpss/furnace_robot": "192.168.1.24",
}

serial_devices_serial_numbers = {
    "gpss/vial_capper": "BG005IB3",
    "gpss/xrd_dispenser_gripper": "BG005CHD",
    "gpss/xrd_dispenser_rail": "BG004CS1",
    "gpss/furnace_A": "B0029FLT",
    "gpss/furnace_B": "B002733Y",
    "gpss/crucible_capper": "BG00U7A3",
    "gpss/dac": "B0029CTO",
    "gpss/shaker_rail": "BG00UA70",
    "gpss/xrd_dispenser_shaker": "7513030383535170D1B2",
}

step_motor_firmware_versions = {
    "gpss/transfer_rail": 74711342,
    "gpss/dosing_head_rack": 76022062,
}

alabos_config = AlabOSConfig()
if not alabos_config.is_sim_mode():
    # convert serial numbers to serial ports
    port2sn = {
        port.device: port.serial_number
        for port in list_ports.comports()
        if port.serial_number is not None
    }

    serial_devices_ports = {}
    for name, serial_number in serial_devices_serial_numbers.items():
        for port, sn in port2sn.items():
            if serial_number in sn:
                serial_devices_ports[name] = port
                break
        else:
            raise KeyError(
                f"Device {name} not found in connected devices. "
                f"The serial number is {serial_number}. "
                f"All available serial numbers are {list(port2sn.keys())}"
            )
else:
    # use the serial numbers as the ports
    serial_devices_ports = dict(serial_devices_serial_numbers.items())

add_device(
    AutoBalance(
        ip_address=ethernet_devices_ips["gpss/auto_balance"],
        balance_restarter_ip_address=ethernet_devices_ips["gpss/balance_restarter"],
        name="gpss/auto_balance",
    )
)
add_device(
    BallDispenser(
        ip_address=ethernet_devices_ips["gpss/ball_dispenser"],
        name="gpss/ball_dispenser",
    )
)
add_device(ConsumableRack(name="gpss/consumable_rack"))
add_device(
    CrucibleCapper(
        com_port=serial_devices_ports["gpss/crucible_capper"],
        name="gpss/crucible_capper",
    )
)
add_device(
    DAC(
        com_port=serial_devices_ports["gpss/dac"],
        name="gpss/dac",
    )
)
add_device(
    DosingHeadRack(
        name="gpss/dosing_head_rack",
        firmware_version=step_motor_firmware_versions["gpss/dosing_head_rack"],
    )
)

for _id in ["A", "B"]:
    add_device(
        GPSSBoxFurnace(
            com_port=serial_devices_ports[f"gpss/furnace_{_id}"],
            name=f"gpss/furnace_{_id}",
            door_controller_ip=ethernet_devices_ips["gpss/door_opener"],
            furnace_letter=_id,
        )
    )

add_device(
    GPSSRobotArmFurnace(
        ip=ethernet_devices_ips["gpss/furnace_robot"],
        name="gpss/furnace_robot",
    )
)

add_device(
    GPSSRobotArmPowder(
        ip=ethernet_devices_ips["gpss/powder_robot"],
        name="gpss/powder_robot",
    )
)

add_device(
    Shaker(
        linear_rail_com_port=serial_devices_ports["gpss/shaker_rail"],
        ip_address=ethernet_devices_ips["gpss/shaker_gripper"],
        name="gpss/shaker",
    )
)

add_device(
    TransferRail(
        firmware_version=step_motor_firmware_versions["gpss/transfer_rail"],
        name="gpss/transfer_rail",
    )
)

add_device(
    XRDDispenser(
        name="gpss/xrd_dispenser",
        gripper_port=serial_devices_ports["gpss/xrd_dispenser_gripper"],
        rail_port=serial_devices_ports["gpss/xrd_dispenser_rail"],
        balance_ip=ethernet_devices_ips["gpss/xrd_dispenser_balance"],
        shaker_ip=ethernet_devices_ips["gpss/xrd_dispenser_vibrational_motor"],
        shaker_com_port=serial_devices_ports["gpss/xrd_dispenser_shaker"],
    )
)

add_device(XRDSampleHolderRack(name="gpss/xrd_sample_holder_rack"))

add_device(
    VialCapper(
        name="gpss/vial_capper", com_port=serial_devices_ports["gpss/vial_capper"]
    )
)

add_device(
    LabelPrinter(
        name="gpss/label_printer",
        printer_name="Dymo LabelWriter Wireless",
        sumatra_pdf_path=r"C:\Users\Ceder-Alab\AppData\Local\SumatraPDF\SumatraPDF.exe",
    )
)

for idx in ["A", "B", "C", "D"]:
    add_standalone_sample_position(
        SamplePosition(
            f"gpss/hole_plug_holder/hole_plug/{idx}",
            description=f"Hole plug {idx} in the holder",
        )
    )

add_standalone_sample_position(
    SamplePosition(
        "gpss/cru_holder_near_ball_dispenser/crucible",
        description="Crucible in the holder near the ball dispenser",
    )
)

add_standalone_sample_position(
    SamplePosition(
        "gpss/dac_lid_holder/dac_lid",
        description="DAC lid in the holder",
    )
)

add_standalone_sample_position(
    SamplePosition(
        "gpss/furnace_rack_loading/furnace_rack",
        description="Furnace rack in the loading position",
    )
)

add_standalone_sample_position(
    SamplePosition(
        "gpss/furnace_rack_loading/crucible",
        number=8,
        description="Crucible in the furnace rack loading position",
    )
)

add_standalone_sample_position(
    SamplePosition(
        "gpss/cap_holder/cap", description="Cap in the holder near vial capper"
    )
)
add_standalone_sample_position(
    SamplePosition(
        "gpss/cap_holder/cap_sieved",
        description="Cap with sieve near vial capper",
    )
)

add_task(GPSSAddSample)
add_task(GPSSHeating)
add_task(GPSSMoving)
add_task(GPSSPowderDispensing)
add_task(GPSSPowderMixing)
add_task(GPSSSampleGrindingXRD)
add_task(RemoveSample)
