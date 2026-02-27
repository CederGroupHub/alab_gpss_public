"""This module contains the XRDSampleHolderRack class for managing the transfer rack for XRD sample holders."""

from __future__ import annotations

from enum import Enum

from alab_management.device_view import BaseDevice
from alab_management.sample_view import SamplePosition, SampleView
from bson.objectid import ObjectId


class XRDSampleHolderStatus(Enum):
    clean = "clean"
    in_use = "in_use"
    loaded = "loaded"
    disabled = "disabled"


class XRDSampleHolderRack(BaseDevice):
    """A rack to hold clean and dirty sample holders for XRD."""

    description = "Transfer rack for XRD sample holders."
    all_slots = [f"{slot}{idx}" for slot in ["A", "B", "C", "D"] for idx in range(1, 5)]

    def __init__(self, *args, **kwargs):
        """Initialize the XRDSampleHolderRack object."""
        super().__init__(*args, **kwargs)
        self.connected = False
        self.xrd_sample_holder_status = self.dict_in_database(
            "xrd_sample_holder_status",
            {slot: XRDSampleHolderStatus.clean.name for slot in self.all_slots},
        )
        self.xrd_sample_holder_sample_id = self.dict_in_database(
            "xrd_sample_holder_sample_id",
            {slot: None for slot in self.all_slots},
        )
        self.sample_view = SampleView()

    def connect(self):
        """Connect to the XRDSampleHolderRack."""
        self.connected = True

    def disconnect(self):
        """Disconnect from the XRDSampleHolderRack."""
        self.connected = False

    @property
    def sample_positions(self):
        """Return the sample positions of the XRDSampleHolderRack."""
        return [
            SamplePosition(
                f"xrd_sample_holder/{name}",
                description=f"Slot {name} for XRD sample holder.",
            )
            for name in self.all_slots
        ]

    def is_running(self) -> bool:
        """Return whether the XRDSampleHolderRack is running."""
        return False

    def request_one_clean_sample_holder(self, sample_id: str | ObjectId) -> str | None:
        """Request one clean sample holder."""
        self._check_samples_still_alive()
        sample_id = ObjectId(sample_id)
        if self.get_holder_slot_by_sample_id(sample_id) is not None:
            raise ValueError(
                f"Sample {sample_id} is already in use in slot {self.get_holder_slot_by_sample_id(sample_id)}."
            )
        for slot in self.all_slots:
            if self.xrd_sample_holder_status[slot] == XRDSampleHolderStatus.clean.name:
                self.xrd_sample_holder_status[slot] = XRDSampleHolderStatus.in_use.name
                self.xrd_sample_holder_sample_id[slot] = sample_id
                return slot
        return None

    def get_holder_slot_by_sample_id(self, sample_id: str | ObjectId):
        """Get the holder slot by sample ID."""
        self._check_samples_still_alive()
        sample_id = ObjectId(sample_id)
        for slot in self.all_slots:
            if (
                self.xrd_sample_holder_status[slot] == XRDSampleHolderStatus.in_use.name
                and self.xrd_sample_holder_sample_id[slot] == sample_id
            ):
                return slot
        return None

    def mark_one_xrd_holder_as_loaded(self, sample_id: str | ObjectId):
        """Return one sample holder."""
        self._check_samples_still_alive()
        sample_id = ObjectId(sample_id)
        for slot in self.all_slots:
            if (
                self.xrd_sample_holder_status[slot] == XRDSampleHolderStatus.in_use.name
                and self.xrd_sample_holder_sample_id[slot] == sample_id
            ):
                self.xrd_sample_holder_status[slot] = XRDSampleHolderStatus.loaded.name
                return
        raise ValueError(f"Sample holder with sample ID {sample_id} not found in use.")

    def _check_samples_still_alive(self):
        """Check if the sample ID is still alive."""
        for slot in self.all_slots:
            if self.xrd_sample_holder_status[slot] == XRDSampleHolderStatus.in_use.name:
                sample_id = self.xrd_sample_holder_sample_id[slot]
                try:
                    sample = self.sample_view.get_sample(sample_id)
                except ValueError:
                    print(
                        f"Sample {sample_id} not found in the database. Assume its record has been purged. "
                        f"Marking slot {slot} as loaded for cleaning."
                    )
                    self.xrd_sample_holder_status[slot] = (
                        XRDSampleHolderStatus.loaded.name
                    )
                else:
                    if sample.position is None:
                        print(
                            f"Sample {sample_id} not found anywhere in the lab. Assume its record has been purged. "
                            f"Marking slot {slot} as loaded for cleaning."
                        )
                        self.xrd_sample_holder_status[slot] = (
                            XRDSampleHolderStatus.loaded.name
                        )
