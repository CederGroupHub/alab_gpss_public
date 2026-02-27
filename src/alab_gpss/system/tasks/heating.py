import time

from alab_management.device_view.device import mock

from alab_gpss.system.devices.consumable_rack import ConsumableRack
from alab_gpss.system.devices.crucible_capper import CrucibleCapper
from alab_gpss.system.devices.furnace import GPSSBoxFurnace
from alab_gpss.system.tasks.moving import GPSSMoving
from alab_gpss.utils import GPSSBaseTask


class GPSSHeating(GPSSBaseTask):
    FURNACE_RACK_OFFSET = 2  # first two positions are empty
    """This class represents the GPSSHeating task.

    The heating profile in the task should be a list of [temperature, rate, dwelling time in minutes]
    """

    def __init__(self, heating_profile: list[list[float]], *args, **kwargs):
        """Initialize the GPSSHeating task."""
        super().__init__(*args, **kwargs)
        self.heating_profile = heating_profile

        if not self.is_offline:
            self.priority = 21
            self.lab_view.priority = 21

    def validate(self) -> bool:
        if not 1 <= len(self.samples) <= 6:
            return False
        if any(len(profile) != 3 for profile in self.heating_profile):
            return False
        if len(self.heating_profile) > 8:
            return False
        if any(
            temperature < 0 or temperature > 1100
            for temperature, _, _ in self.heating_profile
        ):
            return False
        if any(rate < 0 or rate > 15 for _, rate, _ in self.heating_profile):
            return False
        return True

    def run(self):
        if msg := GPSSBaseTask.check_if_samples_alive(self):
            return msg

        # increase the priority of the task
        # move the furnace_rack to loading
        # first we need to reserve the gpss/furnace_rack_loading/furnace_rack position
        with self.lab_view.request_resources(
            {
                GPSSBoxFurnace: {
                    "furnace_rack": 1,
                    "crucible": 8,
                    "cooling_area/furnace_rack": 1,
                    "cooling_area/crucible": 8,
                },
            }
        ) as (devices, sample_positions):
            furnace: GPSSBoxFurnace = devices[GPSSBoxFurnace]
            cooling_rack_pos = sample_positions[GPSSBoxFurnace][
                "cooling_area/furnace_rack"
            ][0]
            cooling_crucible_positions = sample_positions[GPSSBoxFurnace][
                "cooling_area/crucible"
            ][self.FURNACE_RACK_OFFSET :]
            in_furnace_rack_position = sample_positions[GPSSBoxFurnace]["furnace_rack"][
                0
            ]
            in_furnace_crucible_positions = sample_positions[GPSSBoxFurnace][
                "crucible"
            ][self.FURNACE_RACK_OFFSET :]
            self.set_message(f"The task is assigned to the furnace {furnace.name}.")

            while furnace.is_running():
                self.set_message(
                    f"The furnace {furnace.name} is currently hot/running. Waiting for it to cool down/finish."
                )
                time.sleep(10)

            with self.lab_view.request_resources(
                {
                    "gpss/furnace_robot": {},
                    "gpss/consumable_rack": {},
                    None: {
                        "gpss/furnace_rack_loading/furnace_rack": 1,
                        "gpss/furnace_rack_loading/crucible": 8,
                    },
                }
            ) as _:
                # move the furnace rack to loading position
                self.run_subtask(
                    GPSSMoving,
                    source=cooling_rack_pos,
                    destination="gpss/furnace_rack_loading/furnace_rack",
                    consum_type="furnace_rack",
                )
                positions2samples = self.loading_crucibles_to_furnace_rack()

                self.set_message(f"Moving crucibles to furnace {furnace.name}.")
                furnace.open_door()
                self.run_subtask(
                    GPSSMoving,
                    source="gpss/furnace_rack_loading/furnace_rack",
                    destination=in_furnace_rack_position,
                    consum_type="furnace_rack",
                )
                for i, sample in enumerate(positions2samples):
                    self.lab_view.move_sample(sample, in_furnace_crucible_positions[i])

            furnace.close_door()

            furnace.run_program(self.heating_profile)
            t0 = time.time()
            temperature_log = {"time_minutes": [], "temperature_celsius": []}
            while furnace.is_running():  # track from program start to cooldown
                current_temp = furnace.get_temperature()
                temperature_log["time_minutes"].append((time.time() - t0) / 60)
                temperature_log["temperature_celsius"].append(current_temp)
                time_elapsed_minutes = int((time.time() - t0) / 60)
                current_temp_num = (
                    float(current_temp)
                    if isinstance(current_temp, (int, float))
                    else 0.0
                )

                self.set_message(
                    f"Temperature: {current_temp_num:.1f} C\n"
                    f"Time elapsed: {time_elapsed_minutes} minutes."
                )
                time.sleep(10)

            for sample in self.samples:
                self.lab_view.update_sample_metadata(
                    sample,
                    {
                        "temperature_log": temperature_log,
                        "heating_profile": self.heating_profile,
                    },
                )

            # move the furnace rack to the cooling rack
            furnace.open_door()
            self.run_subtask(
                GPSSMoving,
                source=in_furnace_rack_position,
                destination=cooling_rack_pos,
                consum_type="furnace_rack",
            )
            for i, sample in enumerate(positions2samples):
                self.lab_view.move_sample(sample, cooling_crucible_positions[i])

            furnace.close_door()

            # cool for 10 minutes
            self.set_message("Cooling down for 10 minutes.")
            mock(return_constant=None)(time.sleep)(600)

            with self.lab_view.request_resources(
                {
                    None: {
                        "gpss/furnace_rack_loading/furnace_rack": 1,
                        "gpss/furnace_rack_loading/crucible": 8,
                    },
                    "gpss/consumable_rack": {},
                    "gpss/furnace_robot": {},
                    "gpss/crucible_capper": {"crucible": 1},
                },
                priority=35,
            ) as (_, sample_positions_):
                # move the furnace rack to the loading position
                self.run_subtask(
                    GPSSMoving,
                    source=cooling_rack_pos,
                    destination="gpss/furnace_rack_loading/furnace_rack",
                    consum_type="furnace_rack",
                )
                for i, sample in enumerate(positions2samples):
                    self.lab_view.move_sample(
                        sample,
                        sample_positions_[None]["gpss/furnace_rack_loading/crucible"][
                            self.FURNACE_RACK_OFFSET :
                        ][i],
                    )

                self.unloading_crucibles_to_consumable_rack(positions2samples)
                # move the furnace rack to the cooling area
                self.run_subtask(
                    GPSSMoving,
                    source="gpss/furnace_rack_loading/furnace_rack",
                    destination=cooling_rack_pos,
                    consum_type="furnace_rack",
                )

    def loading_crucibles_to_furnace_rack(self):
        # assuming_all the crucibles are in the consumable rack

        with self.lab_view.request_resources(
            {
                "gpss/consumable_rack": {},
                "gpss/furnace_robot": {},
            },
            priority=25,
        ) as (devices, _):
            consumable_rack: ConsumableRack = devices["gpss/consumable_rack"]
            furnace_robot = devices["gpss/furnace_robot"]

            crucible_positions = {
                sample: consumable_rack.get_sample_slot(
                    self.lab_view.get_sample(sample).sample_id
                )
                for sample in self.samples
            }

            # group it by level
            position2samples = []
            crucible_positions_grouped = {}

            for sample, (level, row) in crucible_positions.items():
                crucible_positions_grouped.setdefault(level, []).append((sample, row))

            for level, samples in crucible_positions_grouped.items():
                self.set_message(
                    f"Moving crucibles from consumable rack level {level} to furnace rack."
                )
                furnace_robot.open_consumble_rack(level)
                for sample, row in samples:
                    position2samples.append(sample)
                    self.run_subtask(
                        GPSSMoving,
                        samples=[sample],
                        destination=f"gpss/furnace_rack_loading/crucible/{len(position2samples)+self.FURNACE_RACK_OFFSET}",
                        consum_type="crucible",
                    )
                    consumable_rack.take_one_consumable(
                        "crucible", self.lab_view.get_sample(sample).sample_id
                    )
                furnace_robot.close_consumble_rack(level)
        return position2samples

    def unloading_crucibles_to_consumable_rack(self, positions2sample: list[str]):
        with self.lab_view.request_resources(
            {
                "gpss/consumable_rack": {},
                "gpss/furnace_robot": {"gripper_v": 1},
                "gpss/crucible_capper": {"crucible": 1},
                None: {
                    "gpss/hole_plug_holder/hole_plug/D": 1,
                },
            },
        ) as (devices, _):
            consumable_rack: ConsumableRack = devices["gpss/consumable_rack"]
            furnace_robot = devices["gpss/furnace_robot"]
            capper: CrucibleCapper = devices["gpss/crucible_capper"]

            crucible_positions = {
                sample: consumable_rack.get_sample_slot(
                    self.lab_view.get_sample(sample).sample_id
                )
                for sample in positions2sample
            }
            crucible_positions_grouped = {}

            for sample, (level, row) in crucible_positions.items():
                crucible_positions_grouped.setdefault(level, []).append((sample, row))

            for level, samples in crucible_positions_grouped.items():
                self.set_message(
                    f"Moving crucibles from furnace rack to consumable rack level {level}."
                )
                furnace_robot.open_consumble_rack(level)
                for sample, row in samples:
                    # first the crucible needs to go to the capper for calibration
                    # as the furnace rack has a large slot

                    capper.open_fully()
                    self.run_subtask(
                        GPSSMoving,
                        samples=[sample],
                        destination="gpss/crucible_capper/crucible",
                        consum_type="crucible",
                    )
                    capper.calibrate()
                    furnace_robot.capping_crucible()

                    self.run_subtask(
                        GPSSMoving,
                        source="gpss/crucible_capper/crucible",
                        destination="gpss/furnace_robot/gripper_v",
                        consum_type="crucible",
                    )

                    crucible_picked = furnace_robot.check_crucible_picked()
                    if not crucible_picked:
                        self.run_subtask(
                            GPSSMoving,
                            source="gpss/furnace_robot/gripper_v",
                            destination="gpss/hole_plug_holder/hole_plug/D",
                            consum_type="hole_plug",
                        )
                    else:
                        self.lab_view.move_sample(
                            sample, "gpss/furnace_robot/gripper_v"
                        )

                    self.run_subtask(
                        GPSSMoving,
                        samples=[sample],
                        destination=f"gpss/consumable_rack/level_{level}/row_{row}/crucible",
                        consum_type="crucible",
                    )
                    consumable_rack.return_one_consumable(
                        "crucible", self.lab_view.get_sample(sample).sample_id
                    )
                    if not crucible_picked:
                        self.run_subtask(
                            GPSSMoving,
                            source="gpss/hole_plug_holder/hole_plug/D",
                            destination="gpss/furnace_robot/gripper_v",
                            consum_type="hole_plug",
                        )
                        self.run_subtask(
                            GPSSMoving,
                            source="gpss/furnace_robot/gripper_v",
                            destination=f"gpss/consumable_rack/level_{level}/row_{row}/crucible",
                            consum_type="crucible",
                        )
                furnace_robot.close_consumble_rack(level)
