from __future__ import annotations

from enum import Enum

from alab_management.device_view import BaseDevice
from alab_management.sample_view import SamplePosition, SampleView
from bson.objectid import ObjectId


class SlotStatus(Enum):
    filled = "filled"
    in_use = "in_use"
    wait_for_removal = "wait_for_removal"


class ConsumableStatus(Enum):
    available = "available"
    empty = "empty"
    dirty = "dirty"


class ConsumableRack(BaseDevice):
    """A rack complex to hold all the consumables and finished samples."""

    NUM_LEVELS = 7
    NUM_ROWS_PER_LEVEL = 5
    CONSUMABLE_TYPES = [
        "cap",
        "cap_sieved",
        "crucible",
        "vial",
    ]

    description = "A rack complex to hold all the consumables and finished samples."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.slots_status = self.dict_in_database(
            "slots_status",
            {
                f"level_{level}_row_{row}": SlotStatus.filled.name
                for level in range(1, self.NUM_LEVELS + 1)
                for row in range(1, self.NUM_ROWS_PER_LEVEL + 1)
            },
        )
        self.slots_sample_id = self.dict_in_database(
            "slots_sample_id",
            {
                f"level_{level}_row_{row}": None
                for level in range(1, self.NUM_LEVELS + 1)
                for row in range(1, self.NUM_ROWS_PER_LEVEL + 1)
            },
        )
        self.consumable_status = self.dict_in_database(
            "consumable_status",
            {
                f"level_{level}_row_{row}-{consumable_type}": ConsumableStatus.available.name
                for level in range(1, self.NUM_LEVELS + 1)
                for row in range(1, self.NUM_ROWS_PER_LEVEL + 1)
                for consumable_type in self.CONSUMABLE_TYPES
            },
        )

        self.sample_view = SampleView()

        self.connected = False

    def connect(self):
        """Connect to the consumable rack."""
        self.connected = True

    def disconnect(self):
        """Disconnect from the consumable rack."""
        self.connected = False

    @property
    def sample_positions(self):
        """Return the sample positions of the transfer rail."""
        all_positions = []
        for level in range(1, self.NUM_LEVELS + 1):
            for row in range(1, self.NUM_ROWS_PER_LEVEL + 1):
                for consumable_type in self.CONSUMABLE_TYPES:
                    all_positions.append(
                        SamplePosition(
                            f"level_{level}/row_{row}/{consumable_type}",
                            description=f"The position of the consumable rack at level {level}, row {row}, {consumable_type}.",
                        )
                    )
        return all_positions

    def get_slot_status(self, level: int, row: int) -> SlotStatus:
        """Get the status of a slot."""
        return SlotStatus(self.slots_status[f"level_{level}_row_{row}"])

    def get_slot_sample_id(self, level: int, row: int) -> ObjectId | None:
        """Get the sample id of a slot."""
        return self.slots_sample_id[f"level_{level}_row_{row}"]

    def get_consumable_status(
        self, level: int, row: int, consumable_type: str
    ) -> ConsumableStatus:
        """Get the status of a consumable."""
        return ConsumableStatus(
            self.consumable_status[f"level_{level}_row_{row}-{consumable_type}"]
        )

    def set_slot_status(self, level: int, row: int, status: SlotStatus | str):
        """Set the status of a slot."""
        if isinstance(status, str):
            status = SlotStatus(status)
        self.slots_status[f"level_{level}_row_{row}"] = status.name

    def set_slot_sample_id(
        self, level: int, row: int, sample_id: str | ObjectId | None
    ):
        """Set the sample id of a slot."""
        if isinstance(sample_id, str):
            sample_id = ObjectId(sample_id)
        self.slots_sample_id[f"level_{level}_row_{row}"] = sample_id

    def set_consumable_status(
        self, level: int, row: int, consumable_type: str, status: ConsumableStatus | str
    ):
        """Set the status of a consumable."""
        if isinstance(status, str):
            status = ConsumableStatus(status)
        self.consumable_status[f"level_{level}_row_{row}-{consumable_type}"] = (
            status.name
        )

    def request_one_empty_slot(self, sample_id: str | ObjectId):
        """Request one empty slot. If there is no empty slot, return None."""
        self._check_samples_still_alive()
        if self.get_sample_slot(sample_id) != (None, None):
            raise ValueError(
                f"Sample {sample_id} is already assigned to a slot. "
                f"Please release it first."
            )

        for level in range(1, self.NUM_LEVELS + 1):
            for row in range(1, self.NUM_ROWS_PER_LEVEL + 1):
                if self.get_slot_status(level, row) == SlotStatus.filled:
                    self.set_slot_status(level, row, SlotStatus.in_use)
                    self.set_slot_sample_id(level, row, sample_id)
                    self.set_message(
                        f"Assign one empty slot (level {level}, row {row}) to sample {sample_id}."
                    )
                    return level, row
        return None, None

    def get_sample_slot(
        self, sample_id: str | ObjectId
    ) -> tuple[int | None, int | None]:
        """Get the slot of a sample."""
        for level in range(1, self.NUM_LEVELS + 1):
            for row in range(1, self.NUM_ROWS_PER_LEVEL + 1):
                if self.get_slot_sample_id(level, row) == sample_id:
                    return level, row
        return None, None

    def take_one_consumable(self, consumable_type: str, sample_id: str | ObjectId):
        """Take one consumable from the rack. Assuming a slot is already reserved for the sample."""
        self._check_samples_still_alive()
        level, row = self.get_sample_slot(sample_id)
        if self.get_slot_status(level, row) != SlotStatus.in_use:
            raise ValueError(f"Slot {level}, {row} is not in use.")
        self.set_consumable_status(level, row, consumable_type, ConsumableStatus.empty)
        self.set_message(
            f"The sample ({sample_id}) has taken one consumable {consumable_type} "
        )

    def return_one_consumable(self, consumable_type: str, sample_id: str | ObjectId):
        """Return one consumable to the rack."""
        self._check_samples_still_alive()
        level, row = self.get_sample_slot(sample_id)
        if self.get_slot_status(level, row) != SlotStatus.in_use:
            raise ValueError(f"Slot {level}, {row} is not in use.")
        if (
            self.get_consumable_status(level, row, consumable_type)
            != ConsumableStatus.empty
        ):
            raise ValueError(
                f"Slot {level}, {row} is not empty. "
                f"Current status : {self.get_consumable_status(level, row, consumable_type)}"
            )
        self.set_consumable_status(level, row, consumable_type, ConsumableStatus.dirty)
        self.set_message(
            f"The sample ({sample_id}) has returned one consumable {consumable_type} "
        )

    def _check_samples_still_alive(self):
        """Check if the samples are still alive."""
        for level in range(1, self.NUM_LEVELS + 1):
            for row in range(1, self.NUM_ROWS_PER_LEVEL + 1):
                if self.get_slot_status(level, row) == SlotStatus.in_use:
                    sample_id = self.get_slot_sample_id(level, row)
                    try:
                        sample = self.sample_view.get_sample(sample_id)
                    except ValueError:
                        print(
                            f"Sample {sample_id} not found in the database. Assume its record has "
                            f"been purged. Marking slot {level}, {row} as waiting for removal."
                        )
                        self._mark_slot_as_dirty(level, row)
                    else:
                        if sample.position is None:
                            print(
                                f"Sample {sample_id} has been moved out of the lab. "
                                f"Marking slot {level}, {row} as waiting for removal."
                            )
                            self._mark_slot_as_dirty(level, row)

    def _mark_slot_as_dirty(self, level: int, row: int):
        """Mark a slot as dirty."""
        if self.get_slot_status(level, row) == SlotStatus.in_use:
            self.set_slot_status(level, row, SlotStatus.wait_for_removal)
            self.set_message(f"Slot {level}, {row} is marked as dirty.")
        else:
            raise ValueError(f"Slot {level}, {row} is not in use.")

    def mark_slot_as_dirty(self, sample_id: str | ObjectId):
        """Mark a slot as dirty."""
        self._check_samples_still_alive()
        level, row = self.get_sample_slot(sample_id)
        self._mark_slot_as_dirty(level, row)

    def release_slot_as_unused(self, level: int, row: int):
        """
        This method is used for aborting the AddingSample task.
        """
        self._check_samples_still_alive()
        if self.get_slot_status(level, row) == SlotStatus.in_use:
            self.set_slot_status(level, row, SlotStatus.filled)
            self.set_slot_sample_id(level, row, None)
            self.set_message(f"Slot {level}, {row} is marked as dirty.")
        else:
            raise ValueError(f"Slot {level}, {row} is not in use.")

    def clean_slot(self, level: int, row: int):
        """Clean a slot."""
        self._check_samples_still_alive()
        if self.get_slot_status(level, row) == SlotStatus.wait_for_removal:
            sample_id = self.get_slot_sample_id(level, row)
            if sample_id is None:
                raise ValueError(f"Slot {level}, {row} has no sample id.")
            try:
                sample = self.sample_view.get_sample(sample_id)
                self.sample_view.move_sample(sample.sample_id, None)
            except ValueError:
                print(
                    f"Sample {sample_id} not found in the database. Assume its record has "
                    f"been purged. Marking slot {level}, {row} as waiting for removal."
                )
            self.set_slot_sample_id(level, row, None)
            for consumable_type in self.CONSUMABLE_TYPES:
                self.set_consumable_status(
                    level, row, consumable_type, ConsumableStatus.available
                )
            self.set_slot_status(level, row, SlotStatus.filled)
        else:
            raise ValueError(f"Slot {level}, {row} is not waiting for removal.")

    def is_running(self):
        """Check if the consumable rack is running."""
        return False
