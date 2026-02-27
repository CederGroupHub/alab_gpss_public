import threading
import time

from alab_management import mock

from alab_gpss.system import BallDispenser, VialCapper
from alab_gpss.system.devices.consumable_rack import ConsumableRack
from alab_gpss.system.devices.crucible_capper import CrucibleCapper
from alab_gpss.system.devices.robot_arm import GPSSRobotArmFurnace, GPSSRobotArmPowder
from alab_gpss.system.devices.shaker import Shaker
from alab_gpss.system.devices.transfer_rail import TransferRail
from alab_gpss.system.devices.xrd_dispenser import XRDDispenser
from alab_gpss.system.devices.xrd_sample_holder_rack import XRDSampleHolderRack
from alab_gpss.system.tasks.moving import GPSSMoving
from alab_gpss.utils import GPSSBaseTask


class GPSSSampleGrindingXRD(GPSSBaseTask):
    def __init__(
        self,
        grinding_time_sec: int,
        frequency: int = 27,
        num_balls: int = 2,
        xrd_dispense_target_mass_mg: float = 20,
        *args,
        **kwargs,
    ):
        """Initialize the GPSSSampleGrindingXRD task."""
        super().__init__(*args, **kwargs)
        self.grinding_time_sec = grinding_time_sec
        self.frequency = frequency
        self.num_balls = num_balls
        self.xrd_dispense_target_mass_mg = xrd_dispense_target_mass_mg

    def validate(self) -> bool:
        if len(self.samples) != 1:
            return False
        if self.grinding_time_sec < 0 or self.grinding_time_sec > 600:
            return False
        if self.frequency < 0 or self.frequency > 35:
            return False
        if self.num_balls < 0 or self.num_balls > 20:
            return False
        if (
            self.xrd_dispense_target_mass_mg < 0
            or self.xrd_dispense_target_mass_mg > 1000
        ):
            return False
        return True

    def run(self):
        if msg := GPSSBaseTask.check_if_samples_alive(self):
            return msg

        self.get_xrd_holder()
        decap_balls_success, decap_after_shaking_success, error_message = (
            self.shake_and_dump_cru(dump_only=False)
        )
        while not decap_after_shaking_success:
            with self.lab_view.request_resources(
                {
                    "gpss/consumable_rack": {},
                }
            ) as (devices, sample_positions):
                consumable_rack: ConsumableRack = devices["gpss/consumable_rack"]
                assigned_slot = consumable_rack.get_sample_slot(
                    self.lab_view.get_sample(self.samples[0]).sample_id
                )
                assigned_level, assigned_row = assigned_slot
            response = self.lab_view.request_user_input(
                f"{error_message} Please manually check the crucible "
                f"at level {assigned_level}, row: {assigned_row}.",
                options=["Retry", "Cancel"],
            )
            if response == "Cancel":
                raise Exception("User cancelled the task.")

            decap_balls_success, decap_after_shaking_success, error_message = (
                self.shake_and_dump_cru(dump_only=decap_balls_success)
            )

        enough_powder = False
        dispensed_failed = False
        while not enough_powder:
            with self.lab_view.request_resources(
                {
                    None: {
                        "gpss/cap_holder/cap": 1,
                        "gpss/cap_holder/cap_sieved": 1,
                    },
                    "gpss/vial_capper": {"vial": 1},
                    "gpss/xrd_dispenser": {"vial": 1, "xrd_sample_holder": 1},
                    "gpss/xrd_sample_holder_rack": {},
                }
            ) as (_, _):
                if dispensed_failed:
                    self.move_caps_vials_to_powder_side()
                else:
                    self.move_crucible_back_move_caps_vials_to_powder_side()
                self.cap_vial(cap_type="cap_sieved")
                amount_dispensed: float = self.prepare_xrd_sample()
                enough_powder = (
                    amount_dispensed >= self.xrd_dispense_target_mass_mg * 0.9
                )
                dispensed_failed = not enough_powder
                if enough_powder:
                    self.uncap_vial(cap_type="cap_sieved", dispose=True)
                    self.cap_vial(cap_type="cap")
                    self.move_vial_back_to_consumable_rack(move_caps=False)
                else:
                    self.uncap_vial(cap_type="cap_sieved")
                    self.move_vial_back_to_consumable_rack(move_caps=True)

                _is_mocking = mock(return_constant=1)(lambda: 0)()
                if not dispensed_failed or _is_mocking:
                    break

            sample_obj = self.lab_view.get_sample(self.samples[0])

            with self.lab_view.request_resources(
                {
                    "gpss/consumable_rack": {},
                }
            ) as (devices, sample_positions):
                consumable_rack = devices["gpss/consumable_rack"]

                assigned_slot = consumable_rack.get_sample_slot(sample_obj.sample_id)
                assigned_level, assigned_row = assigned_slot

            response = self.lab_view.request_user_input(
                f"Not enough powder dispensed ({amount_dispensed:.1f} mg) for sample "
                f"({sample_obj.sample_id}, {sample_obj.name}) at level {assigned_level}, "
                f"row: {assigned_row} of the consumable rack. "
                f"Scrape the powder manually. "
                f"Click 'Retry' to try again or 'Skip' to skip this sample.",
                options=["Retry", "Skip"],
            )

            if response == "Skip":
                break

        self.mark_xrd_holder_as_loaded()

    def shake_and_dump_cru(self, dump_only: bool = False):
        sample = self.samples[0]

        with self.lab_view.request_resources(
            {
                "gpss/shaker": {"crucible": 1, "vial": 1, "dumping/crucible": 1},
                "gpss/crucible_capper": {"crucible": 1},
                "gpss/ball_dispenser": {"crucible": 1},
                None: {
                    "gpss/cru_holder_near_ball_dispenser/crucible": 1,
                    "gpss/hole_plug_holder/hole_plug/B": 1,
                },
            }
        ) as (devices, sample_positions):
            hole_plug = sample_positions[None]["gpss/hole_plug_holder/hole_plug/B"][0]
            shaker: Shaker = devices["gpss/shaker"]
            ball_dispenser: BallDispenser = devices["gpss/ball_dispenser"]

            is_crucible_picked = self.take_out_crucible_and_vial_from_consumable_rack()

            if not is_crucible_picked:
                return (
                    False,
                    False,
                    "Failed to pick up the crucible from the consumable rack. You need to add a new cap to the crucible.",
                )

            if not dump_only:
                is_crucible_picked = True
                if self.num_balls > 0:
                    if self.decap_crucible_with_error_handling(hole_plug):

                        self.set_message("Dispensing balls to the crucible.")
                        with self.lab_view.request_resources(
                            {
                                "gpss/furnace_robot": {},
                            }
                        ):
                            self.run_subtask(
                                GPSSMoving,
                                samples=[sample],
                                destination="gpss/ball_dispenser/crucible",
                                consum_type="crucible",
                            )
                            ball_dispenser.dispense_many(self.num_balls)
                            self.run_subtask(
                                GPSSMoving,
                                samples=[sample],
                                destination="gpss/cru_holder_near_ball_dispenser/crucible",
                                consum_type="crucible",
                            )
                        self.set_message(
                            f"Dispensed {self.num_balls} balls to the crucible."
                        )
                        self.cap_crucible(hole_plug)
                        is_crucible_picked = self.move_capped_crucible_to_cru_holder(
                            dispose_failed_cap=False
                        )
                    else:
                        return (
                            False,
                            False,
                            "Failed to decap the crucible for ball dispensing. You should try to pull out the crucible cap manually.",
                        )

                self.shaking_crucible(
                    shaker=shaker, push_cap_before_shaking=not is_crucible_picked
                )
                self.run_subtask(
                    GPSSMoving,
                    samples=[sample],
                    destination="gpss/cru_holder_near_ball_dispenser/crucible",
                    consum_type="crucible",
                )
            if not self.decap_crucible_with_error_handling(hole_plug):
                return (
                    True,
                    False,
                    "Failed to decap the crucible for dumping. You should try to pull out the crucible cap manually.",
                )
            self.set_message("Start to dumping powder from crucible to the vial.")
            shaker.move_rail_to_dumping_position()
            with self.lab_view.request_resources(
                {
                    "gpss/furnace_robot": {},
                }
            ) as (devices_, _):
                furnace_robot: GPSSRobotArmFurnace = devices_["gpss/furnace_robot"]
                self.run_subtask(
                    GPSSMoving,
                    samples=[sample],
                    destination="gpss/furnace_robot/gripper_hdac",
                    consum_type="crucible",
                )

                # do it twice to make sure all balls are dumped
                for i in range(2):
                    furnace_robot.dumping_balls()
                self.run_subtask(
                    GPSSMoving,
                    samples=[sample],
                    destination="gpss/shaker/dumping/crucible",
                    consum_type="crucible",
                )

                self.set_message("Tapping for 15 seconds.")
                # tapping mode
                shaker.shake(15, 20, close_gripper=False)
                self.run_subtask(
                    GPSSMoving,
                    samples=[sample],
                    destination="gpss/cru_holder_near_ball_dispenser/crucible",
                    consum_type="crucible",
                )
                self.run_subtask(
                    GPSSMoving,
                    source=hole_plug,
                    destination="gpss/furnace_robot/gripper_v",
                    consum_type="hole_plug",
                )
                furnace_robot.dispose_hole_plug()
            shaker.move_rail_to_loading_position()

            return True, True, ""

    def take_out_crucible_and_vial_from_consumable_rack(self) -> bool:
        sample = self.samples[0]

        with self.lab_view.request_resources(
            {
                "gpss/furnace_robot": {"gripper_v": 1},
                "gpss/consumable_rack": {},
                "gpss/shaker": {"vial": 1},
            }
        ) as (devices, _):
            furnace_robot: GPSSRobotArmFurnace = devices["gpss/furnace_robot"]
            consumable_rack: ConsumableRack = devices["gpss/consumable_rack"]
            shaker: Shaker = devices["gpss/shaker"]

            assigned_slot = consumable_rack.get_sample_slot(
                self.lab_view.get_sample(sample).sample_id
            )
            assigned_level, assigned_row = assigned_slot

            furnace_robot.open_consumble_rack(assigned_level)

            self.run_subtask(
                GPSSMoving,
                source=f"gpss/consumable_rack/level_{assigned_level}/row_{assigned_row}/crucible",
                destination="gpss/furnace_robot/gripper_v",
                consum_type="crucible",
            )
            is_crucible_picked = furnace_robot.check_crucible_picked()

            if not is_crucible_picked:
                # it means the crucible is not picked up successfully.
                # Only the cap is picked
                furnace_robot.dispose_hole_plug()
                furnace_robot.close_consumble_rack(assigned_level)
                return False
            # We have to move the sample manually in the database
            self.lab_view.move_sample(sample, "gpss/furnace_robot/gripper_v")
            self.run_subtask(
                GPSSMoving,
                samples=[sample],
                destination="gpss/cru_holder_near_ball_dispenser/crucible",
                consum_type="crucible",
            )

            consumable_rack.take_one_consumable(
                "crucible", self.lab_view.get_sample(sample).sample_id
            )

            shaker.move_rail_to_loading_position()
            self.run_subtask(
                GPSSMoving,
                source=f"gpss/consumable_rack/level_{assigned_level}/row_{assigned_row}/vial",
                destination="gpss/shaker/vial",
                consum_type="vial",
            )
            consumable_rack.take_one_consumable(
                "vial", self.lab_view.get_sample(sample).sample_id
            )

            furnace_robot.close_consumble_rack(assigned_level)
            return True

    def return_crucible_and_vial_to_consumable_rack(self):
        sample = self.samples[0]

        with self.lab_view.request_resources(
            {
                "gpss/furnace_robot": {},
                "gpss/consumable_rack": {},
                "gpss/shaker": {"vial": 1},
            }
        ) as (devices, _):
            furnace_robot: GPSSRobotArmFurnace = devices["gpss/furnace_robot"]
            consumable_rack: ConsumableRack = devices["gpss/consumable_rack"]
            shaker: Shaker = devices["gpss/shaker"]

            assigned_slot = consumable_rack.get_sample_slot(
                self.lab_view.get_sample(sample).sample_id
            )
            assigned_level, assigned_row = assigned_slot

            furnace_robot.open_consumble_rack(assigned_level)

            self.run_subtask(
                GPSSMoving,
                samples=[sample],
                destination=f"gpss/consumable_rack/level_{assigned_level}/row_{assigned_row}/crucible",
                consum_type="crucible",
            )
            consumable_rack.return_one_consumable(
                "crucible", self.lab_view.get_sample(sample).sample_id
            )

            shaker.move_rail_to_loading_position()
            self.run_subtask(
                GPSSMoving,
                source="gpss/shaker/vial",
                destination=f"gpss/consumable_rack/level_{assigned_level}/row_{assigned_row}/vial",
                consum_type="vial",
            )
            consumable_rack.return_one_consumable(
                "vial", self.lab_view.get_sample(sample).sample_id
            )

            furnace_robot.close_consumble_rack(assigned_level)

    def decap_crucible_with_error_handling(self, assigned_hole_plug: str):
        """This function assume the crucible is at crucible holder position."""
        self.set_message(f"Uncapping the crucible. Putting lid to {assigned_hole_plug}")
        decapping_result = self.decap_crucible(assigned_hole_plug=assigned_hole_plug)

        if not decapping_result:
            self.set_message("Decapping failed. Please check the crucible capper.")
            self.return_crucible_and_vial_to_consumable_rack()
            return False
        return True

    def move_capped_crucible_to_cru_holder(self, dispose_failed_cap: bool = False):
        sample = self.samples[0]

        with self.lab_view.request_resources(
            {
                "gpss/furnace_robot": {"gripper_v": 1},
                "gpss/crucible_capper": {"crucible": 1},
                None: {
                    "gpss/hole_plug_holder/hole_plug/D": 1,
                    "gpss/cru_holder_near_ball_dispenser/crucible": 1,
                },
            }
        ) as (devices, _):
            furnace_robot: GPSSRobotArmFurnace = devices["gpss/furnace_robot"]
            crucible_capper: CrucibleCapper = devices["gpss/crucible_capper"]

            crucible_capper.open()

            is_picked = furnace_robot.pick_crucible_from_capper()
            if not is_picked:
                if not dispose_failed_cap:
                    self.run_subtask(
                        GPSSMoving,
                        source="gpss/furnace_robot/gripper_v",
                        destination="gpss/hole_plug_holder/hole_plug/D",
                        consum_type="hole_plug",
                    )
                else:
                    furnace_robot.dispose_hole_plug()
                crucible_capper.open()
                self.run_subtask(
                    GPSSMoving,
                    samples=[sample],
                    destination="gpss/cru_holder_near_ball_dispenser/crucible",
                    consum_type="crucible",
                )
                if not dispose_failed_cap:
                    self.run_subtask(
                        GPSSMoving,
                        source="gpss/hole_plug_holder/hole_plug/D",
                        destination="gpss/furnace_robot/gripper_v",
                        consum_type="hole_plug",
                    )
                    furnace_robot.capping_crucible_on_crucible_holder()
            else:
                # We have to move the sample manually in the database
                self.lab_view.move_sample(sample, "gpss/furnace_robot/gripper_v")
                self.run_subtask(
                    GPSSMoving,
                    samples=[sample],
                    destination="gpss/cru_holder_near_ball_dispenser/crucible",
                    consum_type="crucible",
                )
            return is_picked

    def decap_crucible(self, assigned_hole_plug: str):
        sample = self.samples[0]

        with self.lab_view.request_resources(
            {
                "gpss/furnace_robot": {"gripper_v": 1},
                "gpss/crucible_capper": {"crucible": 1},
            }
        ) as (devices, _):
            furnace_robot: GPSSRobotArmFurnace = devices["gpss/furnace_robot"]
            crucible_capper: CrucibleCapper = devices["gpss/crucible_capper"]

            crucible_capper.open_fully()

            is_picked = furnace_robot.pick_crucible_from_crucible_holder()

            if not is_picked:
                self.run_subtask(
                    GPSSMoving,
                    source="gpss/furnace_robot/gripper_v",
                    destination=assigned_hole_plug,
                    consum_type="hole_plug",
                )
                return True
            # We have to move the sample manually in the database
            self.lab_view.move_sample(sample, "gpss/furnace_robot/gripper_v")

            self.run_subtask(
                GPSSMoving,
                samples=[sample],
                destination="gpss/crucible_capper/crucible",
                consum_type="crucible",
            )

            for i in range(8):
                crucible_capper.close()
                furnace_robot.decapping_crucible()
                crucible_capper.close()

                _is_mocking = mock(return_constant=1)(lambda: 0)()
                if crucible_capper.get_position() >= 5 or _is_mocking:
                    break

                self.set_message("Fail to decap the crucible. Retrying.")
                crucible_capper.open_fully()
                # put the crucible back
                self.run_subtask(
                    GPSSMoving,
                    source="gpss/furnace_robot/gripper_v",
                    destination="gpss/crucible_capper/crucible",
                    consum_type="crucible",
                )
            else:
                self.set_message("Failed to decap the crucible. Stopped")
                return False

            self.set_message(
                "Decapping finished. Move the hole plug to the hole plug holder."
            )
            crucible_capper.open()

            self.run_subtask(
                GPSSMoving,
                source="gpss/furnace_robot/gripper_v",
                destination=assigned_hole_plug,
                consum_type="hole_plug",
            )
            return True

    def shaking_crucible(self, shaker: Shaker, push_cap_before_shaking: bool = True):
        sample = self.samples[0]

        def shaking_thread():
            while True:
                try:
                    if push_cap_before_shaking:
                        for _ in range(2):
                            shaker.close_gripper()
                            shaker.open_gripper()
                    shaker.shake(
                        self.grinding_time_sec, self.frequency, close_gripper=True
                    )
                    shaker.open_gripper()
                    break
                except Exception as e:
                    self.set_message(f"Error during shaking: {e}")
                    shaker.emergent_stop()
                    time.sleep(2)
                    shaker.open_gripper()

                    response = self.lab_view.request_user_input(
                        prompt=f"Error during shaking: {e}",
                        options=["Retry", "Cancel"],
                    )

                    if response == "Cancel":
                        raise

        self.set_message("Loading crucible to shaker")
        # load crucible to the shaker
        shaker.open_gripper()
        self.run_subtask(
            GPSSMoving,
            samples=[sample],
            destination="gpss/shaker/crucible",
            consum_type="crucible",
        )
        self.set_message(
            f"Starting shaking, duration: {self.grinding_time_sec}s, frequency: {self.frequency}Hz"
        )
        shaking_thread = threading.Thread(target=shaking_thread)
        shaking_thread.start()
        shaking_thread.join()
        self.set_message("Shaking finished. Unloading from shaker")

    def cap_crucible(self, assigned_hole_plug: str):
        sample = self.samples[0]
        self.set_message("Capping crucible")
        with self.lab_view.request_resources(
            {
                "gpss/furnace_robot": {},
                "gpss/crucible_capper": {"crucible": 1},
            }
        ) as (devices, _):
            furnace_robot: GPSSRobotArmFurnace = devices["gpss/furnace_robot"]
            crucible_capper: CrucibleCapper = devices["gpss/crucible_capper"]

            crucible_capper.open_fully()

            self.run_subtask(
                GPSSMoving,
                samples=[sample],
                destination="gpss/crucible_capper/crucible",
                consum_type="crucible",
            )
            crucible_capper.calibrate()
            self.run_subtask(
                GPSSMoving,
                source=assigned_hole_plug,
                destination="gpss/furnace_robot/gripper_v",
                consum_type="hole_plug",
            )
            furnace_robot.capping_crucible()
            crucible_capper.open()

    def move_crucible_back_move_caps_vials_to_powder_side(self):
        sample = self.samples[0]

        with self.lab_view.request_resources(
            {
                "gpss/shaker": {"crucible": 1, "vial": 1},
                "gpss/transfer_rail": {
                    "left/vial": 1,
                    "left/cap": 1,
                    "left/cap_sieved": 1,
                    "right/vial": 1,
                    "right/cap": 1,
                    "right/cap_sieved": 1,
                },
                "gpss/vial_capper": {"vial": 1},
                None: {
                    "gpss/cap_holder/cap": 1,
                    "gpss/cap_holder/cap_sieved": 1,
                },
            },
        ) as (devices, _):
            transfer_rail: TransferRail = devices["gpss/transfer_rail"]
            vial_capper: VialCapper = devices["gpss/vial_capper"]
            transfer_rail.move_to_furnace_side()
            with self.lab_view.request_resources(
                {
                    "gpss/furnace_robot": {},
                    "gpss/consumable_rack": {},
                }
            ) as (devices_, _):

                furnace_robot: GPSSRobotArmFurnace = devices_["gpss/furnace_robot"]
                consumable_rack: ConsumableRack = devices_["gpss/consumable_rack"]

                assigned_level, assigned_row = consumable_rack.get_sample_slot(
                    self.lab_view.get_sample(sample).sample_id
                )
                self.set_message(
                    f"Move the crucible back to the consumable rack. Level: {assigned_level}, row: {assigned_row}"
                )
                furnace_robot.open_consumble_rack(assigned_level)
                self.run_subtask(
                    GPSSMoving,
                    samples=[sample],
                    destination=f"gpss/consumable_rack/level_{assigned_level}/row_{assigned_row}/crucible",
                    consum_type="crucible",
                )

                consumable_rack.return_one_consumable(
                    "crucible", self.lab_view.get_sample(sample).sample_id
                )

                # left is the furnace side
                transfer_rail.move_to_furnace_side()

                self.set_message("Move the vial to the transfer rail.")
                self.run_subtask(
                    GPSSMoving,
                    source="gpss/shaker/vial",
                    destination="gpss/transfer_rail/left/vial",
                    consum_type="vial",
                )

                self.set_message("Move the caps to the transfer rail.")
                for cap in ["cap", "cap_sieved"]:
                    self.run_subtask(
                        GPSSMoving,
                        source=f"gpss/consumable_rack/level_{assigned_level}/row_{assigned_row}/{cap}",
                        destination=f"gpss/transfer_rail/left/{cap}",
                        consum_type=cap,
                    )
                    consumable_rack.take_one_consumable(
                        cap, self.lab_view.get_sample(sample).sample_id
                    )
                furnace_robot.close_consumble_rack(assigned_level)

                transfer_rail.move_to_powder_side()

            with self.lab_view.request_resources(
                {
                    "gpss/powder_robot": {},
                }
            ) as (devices_, _):
                self.set_message("Move the vial to the capper.")
                vial_capper.zero_position()
                vial_capper.open_fully()
                self.run_subtask(
                    GPSSMoving,
                    source="gpss/transfer_rail/right/vial",
                    destination="gpss/vial_capper/vial",
                    consum_type="vial",
                )
                vial_capper.open()
                self.set_message("Move the caps to the cap holders.")
                for cap in ["cap", "cap_sieved"]:
                    self.run_subtask(
                        GPSSMoving,
                        source=f"gpss/transfer_rail/right/{cap}",
                        destination=f"gpss/cap_holder/{cap}",
                        consum_type=cap,
                    )

    def move_caps_vials_to_powder_side(self):
        sample = self.samples[0]

        with self.lab_view.request_resources(
            {
                "gpss/transfer_rail": {
                    "left/vial": 1,
                    "left/cap": 1,
                    "left/cap_sieved": 1,
                    "right/vial": 1,
                    "right/cap": 1,
                    "right/cap_sieved": 1,
                },
                "gpss/vial_capper": {"vial": 1},
                None: {
                    "gpss/cap_holder/cap": 1,
                    "gpss/cap_holder/cap_sieved": 1,
                },
            },
        ) as (devices, _):
            transfer_rail: TransferRail = devices["gpss/transfer_rail"]
            vial_capper: VialCapper = devices["gpss/vial_capper"]
            transfer_rail.move_to_furnace_side()
            with self.lab_view.request_resources(
                {
                    "gpss/furnace_robot": {},
                    "gpss/consumable_rack": {},
                }
            ) as (devices_, _):

                furnace_robot: GPSSRobotArmFurnace = devices_["gpss/furnace_robot"]
                consumable_rack: ConsumableRack = devices_["gpss/consumable_rack"]

                assigned_level, assigned_row = consumable_rack.get_sample_slot(
                    self.lab_view.get_sample(sample).sample_id
                )
                self.set_message(
                    f"Move the crucible back to the consumable rack. Level: {assigned_level}, row: {assigned_row}"
                )
                furnace_robot.open_consumble_rack(assigned_level)

                # left is the furnace side
                transfer_rail.move_to_furnace_side()

                self.set_message("Move the vial to the transfer rail.")
                self.run_subtask(
                    GPSSMoving,
                    source=f"gpss/consumable_rack/level_{assigned_level}/row_{assigned_row}/vial",
                    destination="gpss/transfer_rail/left/vial",
                    consum_type="vial",
                )
                consumable_rack.take_one_consumable(
                    "vial", self.lab_view.get_sample(sample).sample_id
                )

                self.set_message("Move the caps to the transfer rail.")
                for cap in ["cap", "cap_sieved"]:
                    self.run_subtask(
                        GPSSMoving,
                        source=f"gpss/consumable_rack/level_{assigned_level}/row_{assigned_row}/{cap}",
                        destination=f"gpss/transfer_rail/left/{cap}",
                        consum_type=cap,
                    )
                    consumable_rack.take_one_consumable(
                        cap, self.lab_view.get_sample(sample).sample_id
                    )
                furnace_robot.close_consumble_rack(assigned_level)

                transfer_rail.move_to_powder_side()

            with self.lab_view.request_resources(
                {
                    "gpss/powder_robot": {},
                }
            ) as (devices_, _):
                self.set_message("Move the vial to the capper.")
                vial_capper.zero_position()
                vial_capper.open_fully()
                self.run_subtask(
                    GPSSMoving,
                    source="gpss/transfer_rail/right/vial",
                    destination="gpss/vial_capper/vial",
                    consum_type="vial",
                )
                vial_capper.open()
                self.set_message("Move the caps to the cap holders.")
                for cap in ["cap", "cap_sieved"]:
                    self.run_subtask(
                        GPSSMoving,
                        source=f"gpss/transfer_rail/right/{cap}",
                        destination=f"gpss/cap_holder/{cap}",
                        consum_type=cap,
                    )

    def move_vial_back_to_consumable_rack(self, move_caps: bool = False):
        sample = self.samples[0]

        with self.lab_view.request_resources(
            {
                "gpss/transfer_rail": {
                    "left/vial": 1,
                    "left/cap": 1,
                    "left/cap_sieved": 1,
                    "right/vial": 1,
                    "right/cap": 1,
                    "right/cap_sieved": 1,
                },
                "gpss/consumable_rack": {},
                "gpss/vial_capper": {"vial": 1},
            }
        ) as (devices, _):
            transfer_rail: TransferRail = devices["gpss/transfer_rail"]
            consumable_rack: ConsumableRack = devices["gpss/consumable_rack"]

            self.set_message("Move the vial to the transfer rail.")
            transfer_rail.move_to_powder_side()
            self.run_subtask(
                GPSSMoving,
                source="gpss/vial_capper/vial",
                destination="gpss/transfer_rail/right/vial",
                consum_type="vial",
            )
            if move_caps:
                self.set_message("Move the caps to the transfer rail.")
                for cap in ["cap", "cap_sieved"]:
                    self.run_subtask(
                        GPSSMoving,
                        source=f"gpss/cap_holder/{cap}",
                        destination=f"gpss/transfer_rail/right/{cap}",
                        consum_type=cap,
                    )
            transfer_rail.move_to_furnace_side()

            with self.lab_view.request_resources({"gpss/furnace_robot": {}}) as (
                devices_,
                sample_positions,
            ):
                furnace_robot: GPSSRobotArmFurnace = devices_["gpss/furnace_robot"]
                assigned_slot = consumable_rack.get_sample_slot(
                    self.lab_view.get_sample(sample).sample_id
                )
                assigned_level, assigned_row = assigned_slot
                self.set_message(
                    f"Move the vial back to the consumable rack level: {assigned_level}, row: {assigned_row}"
                )
                furnace_robot.open_consumble_rack(assigned_level)
                self.run_subtask(
                    GPSSMoving,
                    source="gpss/transfer_rail/left/vial",
                    destination=f"gpss/consumable_rack/level_{assigned_level}/row_{assigned_row}/vial",
                    consum_type="vial",
                )
                consumable_rack.return_one_consumable(
                    consumable_type="vial",
                    sample_id=self.lab_view.get_sample(sample).sample_id,
                )
                if move_caps:
                    self.set_message("Move the caps back to the consumable rack.")
                    for cap in ["cap", "cap_sieved"]:
                        self.run_subtask(
                            GPSSMoving,
                            source=f"gpss/transfer_rail/left/{cap}",
                            destination=f"gpss/consumable_rack/level_{assigned_level}/row_{assigned_row}/{cap}",
                            consum_type=cap,
                        )
                        consumable_rack.return_one_consumable(
                            consumable_type=cap,
                            sample_id=self.lab_view.get_sample(sample).sample_id,
                        )
                furnace_robot.close_consumble_rack(assigned_level)

    def cap_vial(self, cap_type: str = "cap"):
        with self.lab_view.request_resources(
            {
                None: {
                    "gpss/cap_holder/cap_sieved": 1,
                    "gpss/cap_holder/cap": 1,
                },
                "gpss/vial_capper": {"vial": 1},
                "gpss/powder_robot": {},
            }
        ) as (devices, _):
            powder_robot: GPSSRobotArmPowder = devices["gpss/powder_robot"]
            vial_capper: VialCapper = devices["gpss/vial_capper"]

            self.set_message(f"Putting {cap_type} to the vial.")
            self.run_subtask(
                GPSSMoving,
                source=f"gpss/cap_holder/{cap_type}",
                destination="gpss/powder_robot/gripper_v",
                consum_type=cap_type,
            )
            powder_robot.capping_vial()
            vial_capper.zero_position()
            vial_capper.open_fully()
            self.run_subtask(
                GPSSMoving,
                source="gpss/powder_robot/gripper_v",
                destination="gpss/vial_capper/vial",
                consum_type="vial",
            )
            vial_capper.open()

    def uncap_vial(self, cap_type: str = "cap", dispose: bool = False):
        with self.lab_view.request_resources(
            {
                None: {f"gpss/cap_holder/{cap_type}": 1},
                "gpss/vial_capper": {"vial": 1},
                "gpss/powder_robot": {},
            }
        ) as (devices, _):
            powder_robot: GPSSRobotArmPowder = devices["gpss/powder_robot"]
            self.set_message(f"Uncap {cap_type} from the vial. Disposing: {dispose}")
            powder_robot.decapping_vial()

            self.run_subtask(
                GPSSMoving,
                source="gpss/powder_robot/gripper_v",
                destination=f"gpss/cap_holder/{cap_type}",
                consum_type=cap_type,
            )
            if dispose:
                self.run_subtask(
                    GPSSMoving,
                    source=f"gpss/cap_holder/{cap_type}",
                    destination="gpss/powder_robot/gripper_v",
                    consum_type=cap_type,
                )
                powder_robot.disposing_dirty_caps()

    def prepare_xrd_sample(self):
        sample = self.samples[0]
        with self.lab_view.request_resources(
            {
                "gpss/xrd_dispenser": {"vial": 1, "xrd_sample_holder": 1},
                "gpss/xrd_sample_holder_rack": {},
            }
        ) as (devices, sample_positions):
            xrd_dispenser: XRDDispenser = devices["gpss/xrd_dispenser"]
            xrd_sample_holder_rack: XRDSampleHolderRack = devices[
                "gpss/xrd_sample_holder_rack"
            ]
            xrd_sample_holder_slot = (
                xrd_sample_holder_rack.get_holder_slot_by_sample_id(
                    self.lab_view.get_sample(sample).sample_id
                )
            )

            self.lab_view.update_sample_metadata(
                sample,
                {
                    "xrd_sample_holder_slot": xrd_sample_holder_slot,
                },
            )

            self.set_message(
                f"Take one xrd sample holder from rack to the XRD dispenser. Slot: {xrd_sample_holder_slot}"
            )

            xrd_dispenser.move_to_loading_position()
            self.run_subtask(
                GPSSMoving,
                source=f"gpss/xrd_sample_holder_rack/xrd_sample_holder/{xrd_sample_holder_slot}",
                destination="gpss/xrd_dispenser/xrd_sample_holder",
                consum_type="xrd_sample_holder",
            )

            self.set_message("Move the vial to the XRD dispenser.")

            self.run_subtask(
                GPSSMoving,
                source="gpss/vial_capper/vial",
                destination="gpss/xrd_dispenser/vial",
                consum_type="vial",
            )

            self.set_message("Prepare the powder for XRD.")

            for i in range(4):
                xrd_dispense_history = self.lab_view.get_sample(sample).metadata.get(
                    "xrd_dispense_history", []
                )
                amount_dispensed = sum(
                    entry.get("dispensed_mass", 0) for entry in xrd_dispense_history
                )
                result = xrd_dispenser.dispensing_powder(
                    target_mass=max(
                        self.xrd_dispense_target_mass_mg - amount_dispensed, 5
                    ),
                    tolerance=5,
                    angle_offset=10,
                )
                xrd_dispense_history.append(dict(result))
                amount_dispensed += result.dispensed_mass

                self.lab_view.update_sample_metadata(
                    sample,
                    {
                        "xrd_dispense_history": xrd_dispense_history,
                        "dispensed_mass_mg": amount_dispensed,
                    },
                )

                # stop if enough powder is dispensed or no powder at all (<3mg).
                if result.mass_reached:
                    break

            xrd_dispenser.move_to_loading_position()

            self.set_message("Move the vial back to vial capper.")

            with self.lab_view.request_resources(
                {
                    "gpss/vial_capper": {"vial": 1},
                }
            ) as (devices_, _):
                vial_capper: VialCapper = devices_["gpss/vial_capper"]
                vial_capper.zero_position()
                vial_capper.open_fully()
                self.run_subtask(
                    GPSSMoving,
                    source="gpss/xrd_dispenser/vial",
                    destination="gpss/vial_capper/vial",
                    consum_type="vial",
                )
                vial_capper.open()

            self.set_message("Move the xrd sample holder back to the rack.")

            self.run_subtask(
                GPSSMoving,
                source="gpss/xrd_dispenser/xrd_sample_holder",
                destination=f"gpss/xrd_sample_holder_rack/xrd_sample_holder/{xrd_sample_holder_slot}",
                consum_type="xrd_sample_holder",
            )

            return amount_dispensed

    def get_xrd_holder(self):
        while True:
            with self.lab_view.request_resources(
                {
                    "gpss/xrd_sample_holder_rack": {},
                },
                priority=15,
            ) as (devices, sample_positions):
                xrd_sample_holder_rack: XRDSampleHolderRack = devices[
                    "gpss/xrd_sample_holder_rack"
                ]

                xrd_sample_holder_slot = (
                    xrd_sample_holder_rack.request_one_clean_sample_holder(
                        self.lab_view.get_sample(self.samples[0]).sample_id
                    )
                )

                if xrd_sample_holder_slot is None:
                    self.set_message(
                        "Waiting for xrd sample holder to be available. Sleep for 60 seconds"
                    )
                    time.sleep(60)
                else:
                    self.set_message(
                        f"Using xrd sample holder {xrd_sample_holder_slot}"
                    )
                    return xrd_sample_holder_slot

    def mark_xrd_holder_as_loaded(self):
        sample = self.samples[0]
        with self.lab_view.request_resources(
            {
                "gpss/xrd_sample_holder_rack": {},
            }
        ) as (devices, sample_positions):
            xrd_sample_holder_rack: XRDSampleHolderRack = devices[
                "gpss/xrd_sample_holder_rack"
            ]

            xrd_sample_holder_rack.mark_one_xrd_holder_as_loaded(
                self.lab_view.get_sample(sample).sample_id
            )
