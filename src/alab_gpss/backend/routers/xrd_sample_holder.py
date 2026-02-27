"""Router for XRD sample holder rack."""

import contextlib
import re
import time
from pathlib import Path
from traceback import format_exc
from typing import List, Optional

import requests
import win32netcon
import win32wnet
from alab_control.diffractometer_aeris import Aeris
from alab_management.sample_view import SampleView
from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from requests.auth import HTTPBasicAuth

from alab_gpss.system.devices.xrd_sample_holder_rack import XRDSampleHolderRack, XRDSampleHolderStatus


@contextlib.contextmanager
def network_share(unc_path: str, username: str, password: str, domain: str | None = None):
    """
    Temporarily connects to a UNC share with credentials.
    Example unc_path: r"\\192.168.1.15\\AerisData"
    """
    user = f"{domain}\\{username}" if domain else username

    netresource = win32wnet.NETRESOURCE()
    netresource.dwType = win32netcon.RESOURCETYPE_DISK
    netresource.lpLocalName = None  # No drive letter
    netresource.lpRemoteName = unc_path
    netresource.lpProvider = None

    # Disconnect any previously established connection for this user and path
    try:
        win32wnet.WNetCancelConnection2(unc_path, 0, True)
    except Exception:
        pass  # Ignore errors if not connected

    try:
        win32wnet.WNetAddConnection2(netresource, password, user, 0)
        yield
    finally:
        try:
            win32wnet.WNetCancelConnection2(unc_path, 0, True)
        except Exception:
            pass


router = APIRouter()

# Create a global instance of the XRD sample holder rack
xrd_sample_holder_rack = XRDSampleHolderRack(name="gpss/xrd_sample_holder_rack")

# Initialize sample view for database operations
sample_view = SampleView()

# Global measurement tracking
current_measurement = {
    "is_running": False,
    "row": None,
    "progress": 0,
    "current_slot": None,
    "total_slots": 0,
    "status": "idle",
    "completed_at": None,
    "success": None,
}


class SlotStatus(BaseModel):
    """Model for slot status."""

    slot: str
    status: str
    sample_id: Optional[str] = None
    sample_name: Optional[str] = None


class MeasurementProgress(BaseModel):
    """Model for measurement progress."""

    is_running: bool
    row: Optional[str] = None
    progress: int
    current_slot: Optional[str] = None
    total_slots: int
    status: str
    completed_at: Optional[str] = None
    success: Optional[bool] = None


def get_measurement_name(holder_info) -> str:
    """Generate measurement name from holder info."""
    sample_name = holder_info["sample_name"]
    sample_id = holder_info["sample_id"]
    return f"GPSS_{sample_name}_{sample_id}"


def submit_to_dara(
    user: str,
    file_path: str,
    precursor_or_element: list,
    use_reaction_network: bool = False,
    temperature_C: int = -1000,
):
    """Submit XRD pattern for analysis to DARA."""
    url = "http://dara.lbl.gov/api/submit"

    with open(file_path, "rb") as f:
        files = {"pattern_file": f}
        data = {
            "user": user,
            "use_rxn_predictor": use_reaction_network,
            "temperature": temperature_C,
            "precursor_formulas": str(precursor_or_element),
        }

        response = requests.post(
            url, files=files, data=data, verify=False
        )

    return response.json()


def add_measurement_to_db(sample_id: ObjectId, measurement_file: Path, dara_wf_id: Optional[str] = None):
    """Add measurement data to database."""
    if dara_wf_id is not None:
        sample_view.update_sample_metadata(
            ObjectId(sample_id),
            {"xrd_measurement": {"xrdml": measurement_file.read_text(encoding="utf-8-sig"), "dara_wf_id": dara_wf_id}},
        )
    else:
        sample_view.update_sample_metadata(
            ObjectId(sample_id), {"xrd_measurement": {"xrdml": measurement_file.read_text(encoding="utf-8-sig")}}
        )


def run_measurement_for_row(row: str):
    """Run XRD measurement for all samples in a row."""
    global current_measurement

    try:
        with network_share(r"\\192.168.1.15\AerisData", "guest", ""):
            # Initialize Aeris
            aeris = Aeris("192.168.1.129", r"\\192.168.1.15\AerisData")

            aeris.ALLOWED_SLOTS = {2: 3, 3: 4, 4: 5, 5: 6}
            for allowed_slot in aeris.ALLOWED_SLOTS:
                is_slot_empty = aeris.is_slot_empty(allowed_slot)
                if not is_slot_empty:
                    try:
                        aeris.remove_by_slot(allowed_slot)
                    except Exception:
                        continue

            # Get all holders for the row
            all_holders = {}
            for slot in xrd_sample_holder_rack.all_slots:
                if slot.startswith(row):
                    status = xrd_sample_holder_rack.xrd_sample_holder_status[slot]
                    sample_id = xrd_sample_holder_rack.xrd_sample_holder_sample_id[slot]
                    sample_name = None

                    if sample_id:
                        try:
                            sample = xrd_sample_holder_rack.sample_view.get_sample(ObjectId(sample_id))
                            sample_name = sample.name
                        except Exception:
                            pass

                    all_holders[slot] = {
                        "slot": slot,
                        "status": status,
                        "sample_id": str(sample_id) if sample_id else None,
                        "sample_name": sample_name,
                    }

            # Filter holders with samples
            holders_with_samples = {k: v for k, v in all_holders.items() if v["sample_id"] is not None}

            if not holders_with_samples:
                current_measurement["status"] = "No samples found in row"
                current_measurement["is_running"] = False
                return

            # Map slots to aeris positions (A1->2, A2->3, A3->4, A4->5)
            holders_info = {}
            for i, (slot, holder_info) in enumerate(holders_with_samples.items()):
                aeris_slot = i + 2  # Start from slot 2
                if aeris_slot <= 5:  # Max slot 5
                    holders_info[aeris_slot] = holder_info

            current_measurement["total_slots"] = len(holders_info)
            current_measurement["status"] = "Running measurements"

            # Process each sample
            for slot_idx, (aeris_slot, holder_info) in enumerate(holders_info.items()):
                current_measurement["current_slot"] = holder_info["slot"]
                current_measurement["progress"] = int((slot_idx / len(holders_info)) * 100)

                sample_name = get_measurement_name(holder_info)

                # Run aeris measurement
                aeris.add(sample_name, aeris_slot)
                aeris.scan_and_return_results(sample_name, program="10-100_8-minutes")

                # Submit to DARA
                pattern_file = Path(aeris.results_dir) / f"{sample_name}.xrdml"

                if pattern_file.exists():
                    time.sleep(3)  # wait for the file to be written
                    add_measurement_to_db(ObjectId(holder_info["sample_id"]), pattern_file)  # save in case of Dara failure

                    # Extract elements from sample name for DARA submission
                    composition = re.sub(r"^GPSS_", "", pattern_file.stem).split("_")[0]
                    elements = list(set(re.findall(r"[A-Z][a-z]?", composition)))

                    response = submit_to_dara("yuxing_gpss", str(pattern_file), elements)
                    if response.get("wf_id", None):
                        add_measurement_to_db(ObjectId(holder_info["sample_id"]), pattern_file, response.get("wf_id", None))
                        current_measurement["status"] = f"Completed {holder_info['slot']}"
                    else:
                        current_measurement["status"] = f"Failed to submit {holder_info['slot']} to DARA"

            # Mark completion
            current_measurement["progress"] = 100
            current_measurement["status"] = "Completed successfully"
            current_measurement["success"] = True
    except Exception:
        current_measurement["status"] = f"Error: {format_exc()}"
        current_measurement["success"] = False
    finally:
        from datetime import datetime

        current_measurement["is_running"] = False
        current_measurement["completed_at"] = datetime.now().isoformat()


@router.get("/", response_model=List[SlotStatus])
async def get_all_slots():
    """Get all slots in the XRD sample holder rack."""
    slots = []
    for slot in xrd_sample_holder_rack.all_slots:
        status = xrd_sample_holder_rack.xrd_sample_holder_status[slot]
        sample_id = xrd_sample_holder_rack.xrd_sample_holder_sample_id[slot]
        sample_name = None

        # Get sample name if sample_id exists
        if sample_id:
            try:
                sample = xrd_sample_holder_rack.sample_view.get_sample(ObjectId(sample_id))
                sample_name = sample.name
            except Exception:
                # If sample not found, keep sample_name as None
                pass

        slots.append(
            SlotStatus(
                slot=slot, status=status, sample_id=str(sample_id) if sample_id else None, sample_name=sample_name
            )
        )
    return slots


@router.get("/measurement-progress/", response_model=MeasurementProgress)
async def get_measurement_progress():
    """Get current measurement progress."""
    return MeasurementProgress(**current_measurement)


@router.get("/{slot}/", response_model=SlotStatus)
async def get_slot(slot: str):
    """Get a specific slot in the XRD sample holder rack."""
    if slot not in xrd_sample_holder_rack.all_slots:
        raise HTTPException(status_code=404, detail=f"Slot {slot} not found")

    status = xrd_sample_holder_rack.xrd_sample_holder_status[slot]
    sample_id = xrd_sample_holder_rack.xrd_sample_holder_sample_id[slot]
    sample_name = None

    # Get sample name if sample_id exists
    if sample_id:
        try:
            sample = xrd_sample_holder_rack.sample_view.get_sample(ObjectId(sample_id))
            sample_name = sample.name
        except Exception:
            # If sample not found, keep sample_name as None
            pass

    return SlotStatus(
        slot=slot, status=status, sample_id=str(sample_id) if sample_id else None, sample_name=sample_name
    )


@router.post("/{slot}/mark-as-clean/")
async def mark_as_clean(slot: str):
    """Mark a slot as clean."""
    if slot not in xrd_sample_holder_rack.all_slots:
        raise HTTPException(status_code=404, detail=f"Slot {slot} not found")

    current_status = xrd_sample_holder_rack.xrd_sample_holder_status[slot]
    if current_status != XRDSampleHolderStatus.loaded.name:
        raise HTTPException(
            status_code=400, detail=f"Cannot mark slot {slot} as clean. Current status: {current_status}"
        )

    xrd_sample_holder_rack.xrd_sample_holder_status[slot] = XRDSampleHolderStatus.clean.name
    xrd_sample_holder_rack.xrd_sample_holder_sample_id[slot] = None

    return {"message": f"Slot {slot} marked as clean"}


@router.post("/{slot}/unload/")
async def unload_slot(slot: str):
    """Unload a sample from a slot."""
    if slot not in xrd_sample_holder_rack.all_slots:
        raise HTTPException(status_code=404, detail=f"Slot {slot} not found")

    current_status = xrd_sample_holder_rack.xrd_sample_holder_status[slot]
    if current_status != XRDSampleHolderStatus.loaded.name:
        raise HTTPException(status_code=400, detail=f"Cannot unload slot {slot}. Current status: {current_status}")

    xrd_sample_holder_rack.xrd_sample_holder_status[slot] = XRDSampleHolderStatus.in_use.name

    return {"message": f"Slot {slot} unloaded"}


@router.post("/{slot}/disable/")
async def disable_slot(slot: str):
    """Disable a slot."""
    if slot not in xrd_sample_holder_rack.all_slots:
        raise HTTPException(status_code=404, detail=f"Slot {slot} not found")

    xrd_sample_holder_rack.xrd_sample_holder_status[slot] = XRDSampleHolderStatus.disabled.name

    return {"message": f"Slot {slot} disabled"}


@router.post("/{slot}/enable/")
async def enable_slot(slot: str):
    """Enable a slot."""
    if slot not in xrd_sample_holder_rack.all_slots:
        raise HTTPException(status_code=404, detail=f"Slot {slot} not found")

    xrd_sample_holder_rack.xrd_sample_holder_status[slot] = XRDSampleHolderStatus.clean.name

    return {"message": f"Slot {slot} enabled"}


@router.post("/row/{row}/clean/")
async def clean_row(row: str):
    """Clean all slots in a row."""
    if row not in ["A", "B", "C", "D"]:
        raise HTTPException(status_code=400, detail=f"Invalid row: {row}. Must be A, B, C, or D.")

    if any(
        xrd_sample_holder_rack.xrd_sample_holder_status[slot] != XRDSampleHolderStatus.loaded.name
        for slot in xrd_sample_holder_rack.all_slots
        if slot.startswith(row)
    ):
        raise HTTPException(status_code=400, detail=f"Cannot clean row {row}. Some slots are not loaded.")

    slots_cleaned = 0
    for idx in range(1, 5):
        slot = f"{row}{idx}"
        if xrd_sample_holder_rack.xrd_sample_holder_status[slot] == XRDSampleHolderStatus.loaded.name:
            xrd_sample_holder_rack.xrd_sample_holder_status[slot] = XRDSampleHolderStatus.clean.name
            xrd_sample_holder_rack.xrd_sample_holder_sample_id[slot] = None
            slots_cleaned += 1

    return {"message": f"Cleaned {slots_cleaned} slots in row {row}"}


@router.post("/row/{row}/disable/")
async def disable_row(row: str):
    """Disable all slots in a row."""
    if row not in ["A", "B", "C", "D"]:
        raise HTTPException(status_code=400, detail=f"Invalid row: {row}. Must be A, B, C, or D.")

    if any(
        xrd_sample_holder_rack.xrd_sample_holder_status[slot] != XRDSampleHolderStatus.clean.name
        for slot in xrd_sample_holder_rack.all_slots
        if slot.startswith(row)
    ):
        raise HTTPException(status_code=400, detail=f"Cannot disable row {row}. Some slots are not clean.")

    slots_disabled = 0
    for idx in range(1, 5):
        slot = f"{row}{idx}"
        xrd_sample_holder_rack.xrd_sample_holder_status[slot] = XRDSampleHolderStatus.disabled.name
        slots_disabled += 1

    return {"message": f"Disabled {slots_disabled} slots in row {row}"}


@router.post("/row/{row}/enable/")
async def enable_row(row: str):
    """Enable all slots in a row."""
    if row not in ["A", "B", "C", "D"]:
        raise HTTPException(status_code=400, detail=f"Invalid row: {row}. Must be A, B, C, or D.")

    if any(
        xrd_sample_holder_rack.xrd_sample_holder_status[slot] != XRDSampleHolderStatus.disabled.name
        for slot in xrd_sample_holder_rack.all_slots
        if slot.startswith(row)
    ):
        raise HTTPException(status_code=400, detail=f"Cannot enable row {row}. Some slots are not disabled.")

    slots_enabled = 0
    for idx in range(1, 5):
        slot = f"{row}{idx}"
        xrd_sample_holder_rack.xrd_sample_holder_status[slot] = XRDSampleHolderStatus.clean.name
        slots_enabled += 1

    return {"message": f"Enabled {slots_enabled} slots in row {row}"}


@router.post("/row/{row}/run-measurement/")
async def run_measurement(row: str, background_tasks: BackgroundTasks):
    """Run XRD measurement for all samples in a row."""
    if row not in ["A", "B", "C", "D"]:
        raise HTTPException(status_code=400, detail=f"Invalid row: {row}. Must be A, B, C, or D.")

    # Check if measurement is already running
    if current_measurement["is_running"]:
        raise HTTPException(status_code=400, detail="A measurement is already running.")

    # Check if row has samples and all slots are in acceptable states
    row_slots = [slot for slot in xrd_sample_holder_rack.all_slots if slot.startswith(row)]
    samples_in_row = [
        slot for slot in row_slots if xrd_sample_holder_rack.xrd_sample_holder_sample_id[slot] is not None
    ]

    if not samples_in_row:
        raise HTTPException(status_code=400, detail=f"No samples found in row {row}.")

    # Check that all slots are in acceptable states (not being used)
    acceptable_states = [
        XRDSampleHolderStatus.loaded.name,
        XRDSampleHolderStatus.clean.name,
        XRDSampleHolderStatus.disabled.name,
    ]
    slots_in_use = [
        slot for slot in row_slots if xrd_sample_holder_rack.xrd_sample_holder_status[slot] not in acceptable_states
    ]

    if slots_in_use:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start measurement. Slots {', '.join(slots_in_use)} in row {row} are currently being used.",
        )

    # Initialize measurement tracking
    current_measurement.update(
        {
            "is_running": True,
            "row": row,
            "progress": 0,
            "current_slot": None,
            "total_slots": len(samples_in_row),
            "status": "Starting measurement",
        }
    )

    # Start measurement in background
    background_tasks.add_task(run_measurement_for_row, row)

    return {"message": f"Started XRD measurement for row {row} with {len(samples_in_row)} samples"}
