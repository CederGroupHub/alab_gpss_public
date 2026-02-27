import time

from alab_gpss.system.devices.consumable_rack import ConsumableRack
from alab_gpss.utils import GPSSBaseTask


class GPSSAddSample(GPSSBaseTask):
    """This class represents the GPSSAddSample task."""

    def __init__(self, notify_user: bool = False, *args, **kwargs):
        """Initialize the GPSSAddSample task."""
        super().__init__(*args, **kwargs)
        self.notify_user = notify_user

    def validate(self) -> bool:
        if len(self.samples) != 1:
            return False
        return True

    def run(self):
        sample = self.samples[0]
        while True:
            with self.lab_view.request_resources(
                {"gpss/consumable_rack": {}}, priority=5
            ) as (
                device,
                _,
            ):
                consumable_rack: ConsumableRack = device["gpss/consumable_rack"]
                assigned_slot = consumable_rack.request_one_empty_slot(
                    self.lab_view.get_sample(sample).sample_id
                )

                if assigned_slot != (None, None):
                    assigned_level, assigned_row = assigned_slot
                    self.set_message(
                        f"The sample is assigned to consumable rack level: {assigned_level}, row: {assigned_row}"
                    )
                    with self.lab_view.request_resources(
                        {
                            "gpss/consumable_rack": {
                                f"level_{assigned_level}/row_{assigned_row}/crucible": 1
                            }
                        }
                    ):
                        self.lab_view.move_sample(
                            sample,
                            f"gpss/consumable_rack/level_{assigned_level}/row_{assigned_row}/crucible",
                        )
                        self.lab_view.update_sample_metadata(
                            sample, {"assigned_consumable_rack_slot": assigned_slot}
                        )

            if assigned_slot != (None, None):
                if self.notify_user:
                    response = self.lab_view.request_user_input(
                        f"Please add sample {sample} to consumable "
                        f"rack level: {assigned_level}, row: {assigned_row}",
                        options=["OK", "Cancel"],
                    )
                    if response == "Cancel":
                        with self.lab_view.request_resources(
                            {"gpss/consumable_rack": {}}
                        ) as (device, _):
                            consumable_rack: ConsumableRack = device[
                                "gpss/consumable_rack"
                            ]
                            consumable_rack.release_slot_as_unused(
                                assigned_level, assigned_row
                            )
                            self.lab_view.move_sample(sample, None)
                        self.set_message("Sample addition cancelled.")
                        raise Exception("Sample addition cancelled.")

                return {
                    "assigned_level": assigned_level,
                    "assigned_row": assigned_row,
                }
            self.set_message("No position available. Wait for 60 seconds and try again")
            time.sleep(60)
