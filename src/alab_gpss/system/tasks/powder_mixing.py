from __future__ import annotations

import threading
import time

from alab_management import mock

from alab_gpss.system.devices.consumable_rack import ConsumableRack
from alab_gpss.system.devices.crucible_capper import CrucibleCapper
from alab_gpss.system.devices.dac import DAC
from alab_gpss.system.tasks.moving import GPSSMoving
from alab_gpss.utils import GPSSBaseTask


class GPSSPowderMixing(GPSSBaseTask):
    def __init__(
        self,
        speed: int | list[int],
        duration_seconds: int | list[int],
        interval_seconds: int = 60,
        *args,
        **kwargs,
    ):
        """Initialize the GPSSPowderMixing task."""
        super().__init__(*args, **kwargs)
        if isinstance(speed, int):
            speed = [speed]
        if isinstance(duration_seconds, int):
            duration_seconds = [duration_seconds]
        self.speed = speed
        self.duration_seconds = duration_seconds
        self.interval_seconds = interval_seconds

    def validate(self) -> bool:
        """Validate the task."""
        if len(self.speed) != len(self.duration_seconds):
            raise ValueError(
                "Speed and duration must have the same length. "
                f"Got {len(self.speed)} and {len(self.duration_seconds)}."
            )
        for speed, duration_seconds in zip(
            self.speed, self.duration_seconds, strict=True
        ):
            if speed < 800 or speed > 1600:
                raise ValueError(
                    f"Speed must be between 800 and 1600 RPM. Got {speed}."
                )
            if duration_seconds < 0 or duration_seconds > 600:
                raise ValueError(
                    f"Duration must be between 0 and 600 seconds. Got {duration_seconds}."
                )

        if self.interval_seconds < 0 or self.interval_seconds > 600:
            raise ValueError(
                f"Interval must be between 0 and 600 seconds. Got {self.interval_seconds}."
            )
        if len(self.samples) != 1:
            raise ValueError("Only one sample is allowed for GPSSPowderMixing.")
        return True

    def run(self):
        """Run the GPSSPowderMixing task."""
        if msg := GPSSBaseTask.check_if_samples_alive(self):
            return msg

        def mixing(dac_: DAC):
            """Run the mixing process on the DAC."""
            for i, (speed, duration_seconds) in enumerate(
                zip(self.speed, self.duration_seconds, strict=True)
            ):
                self.set_message(
                    f"Mixing at {speed} RPM for {duration_seconds} seconds."
                )
                dac_.mixing(
                    speed=speed,
                    time_sec=duration_seconds,
                )
                if self.interval_seconds > 0 and i < len(self.speed) - 1:
                    self.set_message(
                        f"Waiting for {self.interval_seconds} seconds before next mixing."
                    )
                    for _ in range(self.interval_seconds):
                        mock(return_constant=1)(time.sleep)(1)

        sample = self.samples[0]
        with self.lab_view.request_resources(
            {
                "gpss/dac": {"crucible": 1, "dac_lid": 1},
                None: {"gpss/dac_lid_holder/dac_lid": 1},
            }
        ) as (
            device,
            _,
        ):
            dac: DAC = device["gpss/dac"]

            with self.lab_view.request_resources(
                {
                    "gpss/consumable_rack": {},
                    "gpss/furnace_robot": {},
                },
                priority=22,
            ) as (devices, _):
                consumable_rack: ConsumableRack = devices["gpss/consumable_rack"]
                furnace_robot = devices["gpss/furnace_robot"]
                assigned_level, assigned_row = consumable_rack.get_sample_slot(
                    self.lab_view.get_sample(sample).sample_id
                )
                self.set_message(
                    f"Move out crucible from consumable rack level {assigned_level} row {assigned_row}."
                )
                self.run_subtask(
                    GPSSMoving,
                    source="gpss/dac/dac_lid",
                    destination="gpss/dac_lid_holder/dac_lid",
                    consum_type="dac_lid",
                )
                furnace_robot.open_consumble_rack(assigned_level)
                self.run_subtask(
                    GPSSMoving,
                    samples=[sample],
                    destination="gpss/furnace_robot/gripper_v",
                    consum_type="crucible",
                )
                consumable_rack.take_one_consumable(
                    "crucible", self.lab_view.get_sample(sample).sample_id
                )

                self.set_message("Load crucible to DAC. Homing.")
                dac.homing()
                self.run_subtask(
                    GPSSMoving,
                    samples=[sample],
                    destination="gpss/dac/crucible",
                    consum_type="crucible",
                )
                self.run_subtask(
                    GPSSMoving,
                    source="gpss/dac_lid_holder/dac_lid",
                    destination="gpss/dac/dac_lid",
                    consum_type="dac_lid",
                )
                self.set_message(
                    f"DAC start to run at {self.speed} RPM for {self.duration_seconds} seconds."
                )
                mixing_thread = threading.Thread(target=mixing, args=(dac,))
                mixing_thread.start()
                furnace_robot.close_consumble_rack(assigned_level)

            mixing_thread.join()
            self.set_message("DAC finished.")

            with self.lab_view.request_resources(
                {
                    "gpss/crucible_capper": {"crucible": 1},
                    None: {
                        "gpss/hole_plug_holder/hole_plug/C": 1,
                    },
                }
            ) as (devices, _):
                crucible_capper: CrucibleCapper = devices["gpss/crucible_capper"]
                with self.lab_view.request_resources(
                    {
                        "gpss/consumable_rack": {},
                        "gpss/furnace_robot": {
                            "gripper_v": 1,
                        },
                    }
                ) as (devices_, _):
                    consumable_rack: ConsumableRack = devices_["gpss/consumable_rack"]
                    furnace_robot = devices_["gpss/furnace_robot"]
                    assigned_level, assigned_row = consumable_rack.get_sample_slot(
                        self.lab_view.get_sample(sample).sample_id
                    )

                    self.set_message("Move crucible to crucible capper for capping.")
                    dac.homing()
                    crucible_capper.open_fully()
                    self.run_subtask(
                        GPSSMoving,
                        source="gpss/dac/dac_lid",
                        destination="gpss/dac_lid_holder/dac_lid",
                        consum_type="dac_lid",
                    )
                    result = furnace_robot.pick_crucible_from_dac()
                    if not result:
                        self.run_subtask(
                            GPSSMoving,
                            source="gpss/furnace_robot/gripper_v",
                            destination="gpss/hole_plug_holder/hole_plug/C",
                            consum_type="hole_plug",
                        )
                        self.run_subtask(
                            GPSSMoving,
                            samples=[sample],
                            destination="gpss/crucible_capper/crucible",
                            consum_type="crucible",
                        )
                        self.run_subtask(
                            GPSSMoving,
                            source="gpss/hole_plug_holder/hole_plug/C",
                            destination="gpss/furnace_robot/gripper_v",
                            consum_type="hole_plug",
                        )
                    else:
                        # We have to move the sample manually in the database
                        self.lab_view.move_sample(
                            sample, "gpss/furnace_robot/gripper_v"
                        )
                        self.run_subtask(
                            GPSSMoving,
                            samples=[sample],
                            destination="gpss/crucible_capper/crucible",
                            consum_type="crucible",
                        )
                    crucible_capper.calibrate()
                    furnace_robot.capping_crucible()

                    self.run_subtask(
                        GPSSMoving,
                        source="gpss/dac_lid_holder/dac_lid",
                        destination="gpss/dac/dac_lid",
                        consum_type="dac_lid",
                    )
                    self.set_message(
                        f"Move the crucible back to consumable rack level {assigned_level} row {assigned_row}."
                    )
                    furnace_robot.open_consumble_rack(assigned_level)
                    crucible_capper.open()
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
