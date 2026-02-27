from __future__ import annotations

from alab_management import mock

from alab_gpss.system.devices.auto_balance import AutoBalance
from alab_gpss.system.devices.ball_dispenser import BallDispenser
from alab_gpss.system.devices.consumable_rack import ConsumableRack
from alab_gpss.system.devices.crucible_capper import CrucibleCapper
from alab_gpss.system.devices.dosing_head_rack import DosingHeadRack
from alab_gpss.system.devices.robot_arm import GPSSRobotArmFurnace, GPSSRobotArmPowder
from alab_gpss.system.devices.transfer_rail import TransferRail
from alab_gpss.system.tasks.moving import GPSSMoving
from alab_gpss.utils import GPSSBaseTask


class FailToDecapException(Exception):
    """Exception raised when the crucible capper fails to decap the crucible."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class GPSSPowderDispensing(GPSSBaseTask):
    def __init__(
        self,
        chemical_list: dict[str, float],
        tolerance_percent: float | tuple[float, float],
        num_balls: int = 2,
        *args,
        **kwargs,
    ):
        """Initialize the PowderDispensing task."""
        super().__init__(*args, **kwargs)
        self.chemical_list = chemical_list
        self.tolerance_percent = (
            (tolerance_percent, tolerance_percent)
            if isinstance(tolerance_percent, (float, int))
            else tolerance_percent
        )
        self.num_balls = num_balls

    def validate(self) -> bool:
        """Validate the task."""
        if len(self.samples) != 1:
            raise ValueError("Only one sample is allowed for PowderDispensing.")
        if any(v for v in self.chemical_list.values() if v <= 0):
            raise ValueError("All chemical amounts must be positive.")
        if self.num_balls < 0:
            raise ValueError("Number of balls must be positive or zero.")
        if self.tolerance_percent[0] < 0 or self.tolerance_percent[1] < 0:
            raise ValueError("Tolerance percent must be positive.")
        return True

    def run(self):
        if msg := GPSSBaseTask.check_if_samples_alive(self):
            return msg

        sample = self.samples[0]
        while True:
            with self.lab_view.request_resources(
                {"gpss/dosing_head_rack": {}}, priority=30
            ) as (
                devices,
                _,
            ):
                dosing_head_rack: DosingHeadRack = devices["gpss/dosing_head_rack"]
                self.set_message("Checking the dosing head rack.")
                problematic_powders = []
                for powder, amount in self.chemical_list.items():
                    dosing_head_position = dosing_head_rack.search_for_chemical(powder)
                    if dosing_head_position is None:
                        problematic_powders.append(powder)

            if problematic_powders:
                response = self.lab_view.request_user_input(
                    f"Powders {problematic_powders} are not found in the dosing head rack. "
                    f"Please check the rack and click okay to continue.",
                    options=["Okay", "Cancel"],
                )
                if response == "Cancel":
                    raise Exception(
                        "User aborted the task while checking dosing head rack."
                    )
            else:
                break

        all_powder_dispensed = False
        decapped_failed = False
        while not all_powder_dispensed:
            if decapped_failed:
                response = self.lab_view.request_user_input(
                    f"Please check the crucible at {self.lab_view.get_sample(sample).position}. We cannot decap it.",
                    options=["Okay", "Cancel"],
                )
                if response == "Cancel":
                    raise Exception("User aborted the task while decapping crucible.")
            with self.lab_view.request_resources(
                {
                    None: {"gpss/hole_plug_holder/hole_plug/A": 1},
                    "gpss/auto_balance": {"dosing_head": 1},
                    "gpss/dosing_head_rack": {},
                }
            ) as (_, sample_positions):
                hole_plug_position = sample_positions[None][
                    "gpss/hole_plug_holder/hole_plug/A"
                ][0]
                self.set_message(
                    f"Remove the cap of the crucible. Putting the cap to {hole_plug_position}"
                )
                with self.lab_view.request_resources(
                    {
                        None: {"gpss/cru_holder_near_ball_dispenser/crucible": 1},
                        "gpss/crucible_capper": {"crucible": 1},
                    }
                ) as _:
                    try:
                        self.take_from_consumable_rack_and_decap_crucible(
                            sample, assigned_hole_plug=hole_plug_position
                        )
                    except FailToDecapException:
                        # move back the crucible to the consumable rack
                        decapped_failed = True
                        self.set_message(
                            "Failed to decap the crucible. Please check the crucible capper."
                        )
                        self.put_back_to_consumable_rack_crucible(sample)
                        continue

                    if self.num_balls:
                        self.set_message(
                            f"Dispensing {self.num_balls} balls to crucible."
                        )
                        self.dispense_balls_into_crucible()

                problematic_powders = self.dispense_powders()
                all_powder_dispensed = not problematic_powders

                self.set_message(
                    "Powder dispensing finished. Now put the cap back to crucible."
                )
                self.cap_and_put_back_to_consumable_rack_crucible(
                    sample, assigned_hole_plug=hole_plug_position
                )

            if problematic_powders:
                response = self.lab_view.request_user_input(
                    f"Dispensing {problematic_powders} failed. Please check the dosing"
                    f" head rack of these powders. We will retry once you click okay",
                    options=["Okay", "Cancel"],
                )
                if response == "Cancel":
                    raise Exception("User aborted the task while dispensing powder.")

    def dispense_balls_into_crucible(self):
        sample = self.samples[0]
        with self.lab_view.request_resources(
            {
                "gpss/ball_dispenser": {"crucible": 1},
                "gpss/furnace_robot": {},
            }
        ) as (devices, _):
            ball_dispenser: BallDispenser = devices["gpss/ball_dispenser"]

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

    def dispense_powders(self) -> list[str]:
        sample = self.samples[0]
        with self.lab_view.request_resources(
            {
                "gpss/auto_balance": {"dosing_head": 1, "crucible": 1},
                "gpss/dosing_head_rack": {},
            }
        ) as (devices, sample_positions):
            auto_balance: AutoBalance = devices["gpss/auto_balance"]
            dosing_head_rack: DosingHeadRack = devices["gpss/dosing_head_rack"]

            with self.lab_view.request_resources(
                {
                    "gpss/transfer_rail": {"left/crucible": 1, "right/crucible": 1},
                }
            ) as (devices_, _):
                transfer_rail: TransferRail = devices_["gpss/transfer_rail"]
                self.set_message("Move the decapped crucible to the transfer rail.")

                # get ready for loading
                transfer_rail.move_to_furnace_side()
                self.run_subtask(
                    GPSSMoving,
                    samples=[sample],
                    destination="gpss/transfer_rail/left/crucible",
                    consum_type="crucible",
                )
                transfer_rail.move_to_powder_side()
                self.lab_view.move_sample(
                    sample,
                    "gpss/transfer_rail/right/crucible",
                )
                auto_balance.zero()
                self.set_message("Load the crucible to balance.")

                auto_balance.open_door()
                self.run_subtask(
                    GPSSMoving,
                    samples=[sample],
                    destination="gpss/auto_balance/crucible",
                    consum_type="crucible",
                )
                auto_balance.close_door()

            self.set_message("Start dispensing")

            for powder, amount in self.chemical_list.items():
                dosing_head_position = dosing_head_rack.search_for_chemical(powder)
                if dosing_head_position is None:
                    continue

                powder_dispensed = (
                    self.lab_view.get_sample(sample)
                    .metadata.get("powders_dispensed", {})
                    .get(powder, 0)
                )
                amount = amount - powder_dispensed
                if amount <= 0:
                    continue

                # position is like "1A", "14D"
                dosing_head_slot = int(dosing_head_position[:-1])
                dosing_head_rack.move_to_slot(dosing_head_slot)

                # load the dosing head to the balance
                self.run_subtask(
                    GPSSMoving,
                    source=f"gpss/dosing_head_rack/{dosing_head_position}",
                    destination="gpss/auto_balance/dosing_head",
                    consum_type="dosing_head",
                )
                dosing_head_rack.take_dosing_head(dosing_head_position)

                self.set_message(
                    f"Dispensing {amount} g of {powder} powder into the crucible."
                )

                shaking_dosing_head_counter = 0
                while True:
                    powder_dispensed = (
                        self.lab_view.get_sample(sample)
                        .metadata.get("powders_dispensed", {})
                        .get(powder, 0)
                    )
                    amount = amount - powder_dispensed
                    if amount <= 0:
                        continue
                    self.set_message(f"Dispensing {amount} g of {powder} powder.")
                    dispensed_weight, err_msg = auto_balance.automatic_dosing(
                        target_value_g=amount,
                        lower_tolerance_percent=self.tolerance_percent[0],
                        upper_tolerance_percent=self.tolerance_percent[1],
                    )

                    sample_dispensing_history = self.lab_view.get_sample(
                        sample
                    ).metadata.get("dispensing_history", [])
                    sample_dispensing_history.append(
                        {
                            "powder": powder,
                            "target_weight": amount,
                            "dispensed_weight": dispensed_weight,
                            "err_msg": err_msg,
                        }
                    )

                    # update the metadata
                    self.lab_view.update_sample_metadata(
                        sample, {"dispensing_history": sample_dispensing_history}
                    )

                    # update the amount in sample's metadata
                    powders_dispensed = self.lab_view.get_sample(sample).metadata.get(
                        "powders_dispensed", {}
                    )
                    powders_dispensed.setdefault(powder, 0)
                    powders_dispensed[powder] = (
                        powders_dispensed[powder] + dispensed_weight
                    )
                    self.lab_view.update_sample_metadata(
                        sample,
                        {
                            "powders_dispensed": powders_dispensed,
                        },
                    )

                    if err_msg is not None:
                        if (
                            err_msg == "SubstanceFlowTooLow"
                            or err_msg == "PowderTooHard"
                        ):
                            if shaking_dosing_head_counter < 4:
                                shaking_dosing_head_counter += 1
                                with self.lab_view.request_resources(
                                    {
                                        "gpss/auto_balance": {"dosing_head": 1},
                                        "gpss/powder_robot": {},
                                    }
                                ) as (devices_, _):
                                    powder_robot: GPSSRobotArmPowder = devices_[
                                        "gpss/powder_robot"
                                    ]
                                    self.set_message(
                                        f"Shaking dosing head ({powder}) due to {err_msg}"
                                    )
                                    self.run_subtask(
                                        GPSSMoving,
                                        source="gpss/auto_balance/dosing_head",
                                        destination="gpss/powder_robot/gripper_dosing_head",
                                        consum_type="dosing_head",
                                    )
                                    powder_robot.shaking_dosing_head()
                                    self.run_subtask(
                                        GPSSMoving,
                                        source="gpss/powder_robot/gripper_dosing_head",
                                        destination="gpss/auto_balance/dosing_head",
                                        consum_type="dosing_head",
                                    )
                                continue
                            elif err_msg == "SubstanceFlowTooLow":
                                dosing_head_rack.update_dosing_head_status(
                                    dosing_head_position=dosing_head_position,
                                    status="empty",
                                )
                                break
                            elif err_msg == "PowderTooHard":
                                dosing_head_rack.update_dosing_head_status(
                                    dosing_head_position=dosing_head_position,
                                    status="stuck",
                                )
                                break
                        self.set_message(
                            f"Failed to dispense {amount} g of {powder} powder into the crucible due to {err_msg}."
                        )
                        response = self.lab_view.request_user_input(
                            f"Failed to dispense {amount} g of {powder} powder "
                            f"into the crucible. To retry, please put the balance into its home position,"
                            f"put the right dosing head on the balance."
                            f" The error message is: {err_msg}",
                            options=["Abort", "Retry"],
                        )
                        if response == "Abort":
                            raise Exception(
                                "User aborted the task while dispensing powder."
                            )
                    else:
                        # successfully dispensed the powder
                        break

                # put back the dosing head rack
                dosing_head_rack.move_to_slot(dosing_head_slot)
                self.run_subtask(
                    GPSSMoving,
                    source="gpss/auto_balance/dosing_head",
                    destination=f"gpss/dosing_head_rack/{dosing_head_position}",
                    consum_type="dosing_head",
                )
                dosing_head_rack.return_dosing_head(dosing_head_position)

            self.set_message("Dispensing finished.")
            with self.lab_view.request_resources(
                {
                    "gpss/transfer_rail": {"left/crucible": 1, "right/crucible": 1},
                    "gpss/crucible_capper": {"crucible": 1},
                }
            ) as (devices_, _):
                transfer_rail: TransferRail = devices_["gpss/transfer_rail"]
                self.set_message("Move the crucible to the furnace side.")
                transfer_rail.move_to_powder_side()
                with self.lab_view.request_resources(
                    {
                        "gpss/auto_balance": {"crucible": 1},
                    }
                ) as (devices__, _):
                    auto_balance: AutoBalance = devices__["gpss/auto_balance"]
                    auto_balance.open_door()
                    self.run_subtask(
                        GPSSMoving,
                        samples=[sample],
                        destination="gpss/transfer_rail/right/crucible",
                        consum_type="crucible",
                    )
                    auto_balance.close_door()
                transfer_rail.move_to_furnace_side()
                self.lab_view.move_sample(
                    sample,
                    "gpss/transfer_rail/left/crucible",
                )
                self.run_subtask(
                    GPSSMoving,
                    samples=[sample],
                    destination="gpss/crucible_capper/crucible",
                    consum_type="crucible",
                )

        # check if all the powders are dispensed successfully
        all_powder_dispensed = self.lab_view.get_sample(sample).metadata.get(
            "powders_dispensed", {}
        )

        problemetic_powders = []
        for powder, amount in self.chemical_list.items():
            powder_dispensed = all_powder_dispensed.get(powder, 0)
            if powder_dispensed < min(
                amount * (1 - self.tolerance_percent[0] / 100), amount - 0.001
            ):
                problemetic_powders.append(powder)

        return problemetic_powders

    def take_from_consumable_rack_and_decap_crucible(
        self,
        sample: str,
        assigned_hole_plug: str,
    ):
        with self.lab_view.request_resources(
            {
                "gpss/consumable_rack": {},
                "gpss/furnace_robot": {},
                "gpss/crucible_capper": {"crucible": 1},
            }
        ) as (devices, _):
            furnace_robot: GPSSRobotArmFurnace = devices["gpss/furnace_robot"]
            consumable_rack: ConsumableRack = devices["gpss/consumable_rack"]
            crucible_capper: CrucibleCapper = devices["gpss/crucible_capper"]

            assigned_level, assigned_row = consumable_rack.get_sample_slot(
                self.lab_view.get_sample(sample).sample_id
            )
            self.set_message(
                f"Open consumable rack level {assigned_level} to "
                f"take crucible from row {assigned_row}"
            )
            furnace_robot.open_consumble_rack(assigned_level)

            self.set_message(
                f"Take crucible from row {assigned_row} of consumable rack level {assigned_level}"
            )
            crucible_capper.open_fully()
            self.run_subtask(
                GPSSMoving,
                samples=[sample],
                destination="gpss/crucible_capper/crucible",
                consum_type="crucible",
            )
            consumable_rack.take_one_consumable(
                "crucible", self.lab_view.get_sample(sample).sample_id
            )
            self.set_message(f"Close consumable rack level {assigned_level}.")
            furnace_robot.close_consumble_rack(assigned_level)
            self.set_message("Decap the crucible.")
            for _ in range(5):
                crucible_capper.close()
                furnace_robot.decapping_crucible()
                crucible_capper.close()

                # if the crucible is still at the capper, it means success
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
                raise FailToDecapException(
                    "Failed to decap the crucible after 5 attempts."
                )

            self.set_message(
                f"Move the hole plug to the hole plug holder {assigned_hole_plug}."
            )
            self.run_subtask(
                GPSSMoving,
                source="gpss/furnace_robot/gripper_v",
                destination=assigned_hole_plug,
                consum_type="hole_plug",
            )
            crucible_capper.calibrate()
            crucible_capper.open()

    def put_back_to_consumable_rack_crucible(self, sample: str):
        with self.lab_view.request_resources(
            {
                "gpss/furnace_robot": {},
                "gpss/crucible_capper": {"crucible": 1},
                "gpss/consumable_rack": {},
                None: {"gpss/cru_holder_near_ball_dispenser/crucible": 1},
            }
        ) as (devices, _):
            consumable_rack: ConsumableRack = devices["gpss/consumable_rack"]
            furnace_robot: GPSSRobotArmFurnace = devices["gpss/furnace_robot"]
            assigned_level, assigned_row = consumable_rack.get_sample_slot(
                self.lab_view.get_sample(sample).sample_id
            )
            self.set_message(
                f"Put back the crucible to the consumable rack level {assigned_level} row {assigned_row}"
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
            furnace_robot.close_consumble_rack(assigned_level)

    def cap_and_put_back_to_consumable_rack_crucible(
        self,
        sample: str,
        assigned_hole_plug: str,
    ):
        with self.lab_view.request_resources(
            {
                "gpss/furnace_robot": {},
                "gpss/crucible_capper": {"crucible": 1},
                "gpss/consumable_rack": {},
                None: {"gpss/cru_holder_near_ball_dispenser/crucible": 1},
            }
        ) as (devices, _):
            furnace_robot: GPSSRobotArmFurnace = devices["gpss/furnace_robot"]
            crucible_capper: CrucibleCapper = devices["gpss/crucible_capper"]
            consumable_rack: ConsumableRack = devices["gpss/consumable_rack"]

            self.set_message("Cap the crucible.")
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

            assigned_level, assigned_row = consumable_rack.get_sample_slot(
                self.lab_view.get_sample(sample).sample_id
            )
            self.set_message(
                f"Put back the crucible to the consumable rack level {assigned_level} row {assigned_row}"
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
            furnace_robot.close_consumble_rack(assigned_level)
