"""Router for dosing head rack."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alab_gpss.system.devices.dosing_head_rack import DosingHeadRack, DosingHeadStatus

router = APIRouter()

# Create a global instance of the dosing head rack
dosing_head_rack = DosingHeadRack(name="gpss/dosing_head_rack", firmware_version=1)


class DosingHeadInfo(BaseModel):
    """Model for dosing head information."""
    slot: str
    status: str
    chemical: Optional[str] = None


@router.get("/", response_model=List[DosingHeadInfo])
async def get_all_dosing_heads():
    """Get all dosing heads in the rack."""
    dosing_heads = []
    for slot in dosing_head_rack.ALL_SLOTS:
        status = dosing_head_rack.dosing_head_status[slot]
        chemical = dosing_head_rack.dosing_head_chemical[slot]

        dosing_heads.append(DosingHeadInfo(
            slot=slot,
            status=status,
            chemical=chemical
        ))
    return dosing_heads


@router.get("/{slot}/", response_model=DosingHeadInfo)
async def get_dosing_head(slot: str):
    """Get a specific dosing head in the rack."""
    if slot not in dosing_head_rack.ALL_SLOTS:
        raise HTTPException(status_code=404, detail=f"Slot {slot} not found")

    status = dosing_head_rack.dosing_head_status[slot]
    chemical = dosing_head_rack.dosing_head_chemical[slot]

    return DosingHeadInfo(
        slot=slot,
        status=status,
        chemical=chemical
    )


class AddDosingHeadRequest(BaseModel):
    """Model for adding a dosing head."""
    chemical: str


@router.post("/{slot}/add/")
async def add_dosing_head(slot: str, request: AddDosingHeadRequest):
    """Add a dosing head to a slot."""
    if slot not in dosing_head_rack.ALL_SLOTS:
        raise HTTPException(status_code=404, detail=f"Slot {slot} not found")

    current_status = dosing_head_rack.dosing_head_status[slot]
    if current_status != DosingHeadStatus.normal.name:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot add dosing head to slot {slot}. Current status: {current_status}"
        )
    if dosing_head_rack.dosing_head_chemical[slot] is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Slot {slot} already has a dosing head. Current chemical: {dosing_head_rack.dosing_head_chemical[slot]}"
        )

    dosing_head_rack.dosing_head_status[slot] = DosingHeadStatus.normal.name
    dosing_head_rack.dosing_head_chemical[slot] = request.chemical

    return {"message": f"Dosing head added to slot {slot}"}


@router.post("/{slot}/clear-error/")
async def clear_error(slot: str):
    """Clear error state of a dosing head."""
    if slot not in dosing_head_rack.ALL_SLOTS:
        raise HTTPException(status_code=404, detail=f"Slot {slot} not found")

    current_status = dosing_head_rack.dosing_head_status[slot]
    if current_status not in [DosingHeadStatus.stuck.name, DosingHeadStatus.empty.name]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot clear error for slot {slot}. Current status: {current_status}"
        )

    dosing_head_rack.dosing_head_status[slot] = DosingHeadStatus.normal.name

    return {"message": f"Error cleared for slot {slot}"}


@router.post("/{slot}/unload/")
async def unload_dosing_head(slot: str):
    """Unload a dosing head from a slot."""
    if slot not in dosing_head_rack.ALL_SLOTS:
        raise HTTPException(status_code=404, detail=f"Slot {slot} not found")

    current_status = dosing_head_rack.dosing_head_status[slot]
    if current_status != DosingHeadStatus.normal.name:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot unload dosing head from slot {slot}. Current status: {current_status}"
        )

    dosing_head_rack.dosing_head_status[slot] = DosingHeadStatus.normal.name
    dosing_head_rack.dosing_head_chemical[slot] = None

    return {"message": f"Dosing head unloaded from slot {slot}"}
