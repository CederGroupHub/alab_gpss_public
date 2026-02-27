"""Router for consumable rack."""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alab_gpss.system.devices.consumable_rack import ConsumableRack, SlotStatus

router = APIRouter()

# Create a global instance of the consumable rack
consumable_rack = ConsumableRack(name="gpss/consumable_rack")


class ConsumableSlotInfo(BaseModel):
    """Model for consumable slot information."""
    level: int
    row: int
    slot_status: str
    sample_id: Optional[str] = None
    sample_name: Optional[str] = None
    consumable_status: Dict[str, str]


@router.get("/", response_model=List[ConsumableSlotInfo])
def get_all_slots_root():
    """Get all slots in the consumable rack (root endpoint)."""
    return get_all_slots()


@router.get("/slots/", response_model=List[ConsumableSlotInfo])
def get_all_slots():
    """Get all slots in the consumable rack."""
    slots = []
    for level in range(1, consumable_rack.NUM_LEVELS + 1):
        for row in range(1, consumable_rack.NUM_ROWS_PER_LEVEL + 1):
            slot_status = consumable_rack.get_slot_status(level, row)
            sample_id = consumable_rack.get_slot_sample_id(level, row)
            sample_name = None
            if sample_id is not None:
                sample = consumable_rack.sample_view.get_sample(sample_id)
                if sample is not None:
                    sample_name = sample.name
            consumable_status = {
                consumable_type: consumable_rack.get_consumable_status(
                    level, row, consumable_type
                ).name
                for consumable_type in consumable_rack.CONSUMABLE_TYPES
            }
            slots.append(
                ConsumableSlotInfo(
                    level=level,
                    row=row,
                    slot_status=slot_status.name,
                    sample_id=str(sample_id) if sample_id else None,
                    sample_name=sample_name,
                    consumable_status=consumable_status,
                )
            )
    return slots


@router.get("/slots/{level:int}/{row:int}/", response_model=ConsumableSlotInfo)
def get_slot(level: int, row: int):
    """Get a specific slot in the consumable rack."""
    if level < 1 or level > consumable_rack.NUM_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Level {level} is out of range. Must be between 1 and {consumable_rack.NUM_LEVELS}.",
        )
    if row < 1 or row > consumable_rack.NUM_ROWS_PER_LEVEL:
        raise HTTPException(
            status_code=400,
            detail=f"Row {row} is out of range. Must be between 1 and {consumable_rack.NUM_ROWS_PER_LEVEL}.",
        )
    slot_status = consumable_rack.get_slot_status(level, row)
    sample_id = consumable_rack.get_slot_sample_id(level, row)
    sample_name = None
    if sample_id is not None:
        sample = consumable_rack.sample_view.get_sample(sample_id)
        if sample is not None:
            sample_name = sample.name
    consumable_status = {
        consumable_type: consumable_rack.get_consumable_status(
            level, row, consumable_type
        ).name
        for consumable_type in consumable_rack.CONSUMABLE_TYPES
    }
    return ConsumableSlotInfo(
        level=level,
        row=row,
        slot_status=slot_status.name,
        sample_id=str(sample_id) if sample_id else None,
        sample_name=sample_name,
        consumable_status=consumable_status,
    )


@router.post("/{level:int}/{row:int}/clean/")
async def clean_slot(level: int, row: int):
    """Clean a slot in the consumable rack."""
    if level < 1 or level > consumable_rack.NUM_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Level {level} is out of range. Must be between 1 and {consumable_rack.NUM_LEVELS}.",
        )
    if row < 1 or row > consumable_rack.NUM_ROWS_PER_LEVEL:
        raise HTTPException(
            status_code=400,
            detail=f"Row {row} is out of range. Must be between 1 and {consumable_rack.NUM_ROWS_PER_LEVEL}.",
        )
    slot_status = consumable_rack.get_slot_status(level, row)
    if slot_status != SlotStatus.wait_for_removal:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot clean slot at level {level}, row {row}. Current status: {slot_status.name}",
        )
    consumable_rack.clean_slot(level, row)
    return {"message": f"Slot at level {level}, row {row} marked as clean"}


@router.post("/level/{level:int}/clean/")
async def clean_level(level: int):
    """Clean all slots in a level of the consumable rack."""
    if level < 1 or level > consumable_rack.NUM_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Level {level} is out of range. Must be between 1 and {consumable_rack.NUM_LEVELS}.",
        )

    # Check if all slots in the level are in wait_for_removal status
    for row in range(1, consumable_rack.NUM_ROWS_PER_LEVEL + 1):
        slot_status = consumable_rack.get_slot_status(level, row)
        if slot_status != SlotStatus.wait_for_removal:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot clean level {level}. Slot at row {row} is not ready for cleaning. Current status: {slot_status.name}",
            )

    # Clean all slots in the level
    for row in range(1, consumable_rack.NUM_ROWS_PER_LEVEL + 1):
        consumable_rack.clean_slot(level, row)

    return {"message": f"Level {level} cleaned successfully"}
