"""Router for ionic conductivity measurement."""

import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd
from alab_management.sample_view import SampleView
from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alab_gpss.system.devices.biologic import (
    DEFAULT_CA_PARAMS,
    DEFAULT_PEIS_PARAMS,
    BioLogic,
)

router = APIRouter()

# Configuration for the BioLogic device
BIOLOGIC_IP = "192.168.1.33"
DATA_FOLDER = Path(r"E:\ionic_conductivity")
SAMPLE_DIAMETER_MM = 6.5024  # in mm. if it needs to be changed, add it as a parameter to the measurement request in the future.

# Create a global instance of the BioLogic device
biologic_device = BioLogic(ip_address=BIOLOGIC_IP, data_folder=DATA_FOLDER)
biologic_device.connect()
sample_view = SampleView()

# Current measurement storage (only one measurement at a time)
current_measurement = None


class PeisParams(BaseModel):
    """Model for PEIS measurement parameters."""

    initial_frequency: float
    final_frequency: float
    frequency_number: int
    repeat: int


class ElectronicConductivityParams(BaseModel):
    """Model for electronic conductivity measurement parameters."""

    voltages: list[float]  # List of voltages to apply
    durations: list[float]  # List of durations for each voltage (in seconds)


class MeasurementRequest(BaseModel):
    """Model for ionic conductivity measurement request."""

    sample_id: str
    sample_height: float | None = None  # in mm, optional - can be added later
    peis_params: PeisParams
    include_electronic_conductivity: bool = False
    electronic_conductivity_params: ElectronicConductivityParams | None = None


class MeasurementEntry(BaseModel):
    """Model for a single measurement entry in the list."""

    measurement_id: str
    timestamp: str
    filename: str
    sample_height_mm: float | None = None
    sample_diameter_mm: float = SAMPLE_DIAMETER_MM
    data: dict
    peis_params: dict | None = None
    electronic_params: dict | None = None


class MeasurementListResponse(BaseModel):
    """Model for list of measurements for a sample."""

    sample_id: str
    ionic_conductivity_measurements: List[MeasurementEntry] = []
    electronic_conductivity_measurements: List[MeasurementEntry] = []


class MeasurementStatus(BaseModel):
    """Model for current measurement status."""

    sample_id: str
    sample_name: str | None = None
    sample_height: float | None = None
    peis_params: PeisParams
    include_electronic_conductivity: bool = False
    electronic_conductivity_params: ElectronicConductivityParams | None = None
    status: str
    message: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    progress: float = 0.0


class MeasurementResponse(BaseModel):
    """Model for measurement response."""

    sample_id: str
    sample_height: float | None = None
    peis_params: PeisParams
    include_electronic_conductivity: bool = False
    electronic_conductivity_params: ElectronicConductivityParams | None = None
    status: str
    message: str


class PlotData(BaseModel):
    """Model for plot data response in Plotly JSON format."""

    data: list[dict]  # Array of trace objects
    layout: dict  # Layout configuration object


class DefaultParametersResponse(BaseModel):
    """Model for default measurement parameters."""

    peis_params: PeisParams
    electronic_conductivity_params: ElectronicConductivityParams


class UpdateSampleHeightRequest(BaseModel):
    """Model for updating sample height of current measurement."""

    sample_height: float  # in mm


class LoadSampleRequest(BaseModel):
    """Model for loading an existing sample measurement."""

    sample_id: str
    ionic_measurement_id: str | None = None  # Specific measurement to load
    electronic_measurement_id: str | None = None  # Specific measurement to load


def generate_measurement_id() -> str:
    """Generate a unique measurement ID."""
    return f"meas_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"


def get_sample_name(sample_id: str) -> str | None:
    """Helper function to get sample name from sample ID."""
    try:
        sample_id_obj = ObjectId(sample_id)
        sample = sample_view.get_sample(sample_id_obj)
        return sample.name
    except Exception as e:
        print(f"Warning: Could not fetch sample name for {sample_id}: {e}")
        return None


def run_measurement(
    sample_id: str,
    sample_height: float | None,
    peis_params: PeisParams,
    include_electronic_conductivity: bool = False,
    electronic_conductivity_params: ElectronicConductivityParams | None = None,
):
    """Run the actual measurement in a background thread."""
    global current_measurement

    try:
        # Update measurement status to running
        current_measurement["status"] = "running"
        current_measurement["started_at"] = datetime.now().isoformat()
        current_measurement["progress"] = 0.1
        current_measurement["message"] = "Starting measurement..."

        # Check if device is already running
        if biologic_device.is_running():
            current_measurement["status"] = "failed"
            current_measurement["error"] = (
                "BioLogic device is currently running another measurement"
            )
            current_measurement["completed_at"] = datetime.now().isoformat()
            return

        current_measurement["progress"] = 0.2
        current_measurement["message"] = "Connecting to device..."

        # Generate measurement IDs
        ionic_measurement_id = generate_measurement_id()
        electronic_measurement_id = (
            generate_measurement_id() if include_electronic_conductivity else None
        )

        # Get current timestamp
        measurement_timestamp = datetime.now().isoformat()

        # Calculate progress steps
        total_measurements = 1 + (1 if include_electronic_conductivity else 0)
        progress_step = 0.7 / total_measurements

        # Run ionic conductivity measurement
        current_measurement["progress"] = 0.3
        current_measurement["message"] = "Running ionic conductivity measurement..."

        # Start measurement with provided PEIS parameters
        measurement_params = {
            "voltage": 0,
            "final_frequency": peis_params.final_frequency,
            "initial_frequency": peis_params.initial_frequency,
            "amplitude_voltage": 10,
            "frequency_number": peis_params.frequency_number,
            "duration": 0,
            "repeat": peis_params.repeat,
            "wait": 0.1,
        }

        # Perform the ionic conductivity measurement
        ionic_data = biologic_device.measure_ionic_conductivity(
            params=measurement_params
        )

        # Generate filename for ionic conductivity
        ionic_filename = f"ionic_conductivity_{sample_id}_{ionic_measurement_id}_{biologic_device.ip_address}.csv"

        # Create ionic conductivity measurement entry
        ionic_entry = {
            "measurement_id": ionic_measurement_id,
            "timestamp": measurement_timestamp,
            "filename": ionic_filename,
            "sample_height_mm": sample_height,
            "sample_diameter_mm": SAMPLE_DIAMETER_MM,
            "data": ionic_data.to_dict(orient="list"),
            "peis_params": measurement_params,
        }

        current_measurement["progress"] = 0.3 + progress_step

        # Prepare metadata updates
        metadata_updates = {}

        # Handle ionic conductivity list
        sample_id_obj = ObjectId(sample_id)
        sample = sample_view.get_sample(sample_id_obj)

        # Get existing ionic conductivity measurements or create new list
        existing_ionic = sample.metadata.get("ionic_conductivity_measurements", [])
        if not isinstance(existing_ionic, list):
            # Handle legacy single measurement format
            if "ionic_conductivity" in sample.metadata:
                legacy_data = sample.metadata["ionic_conductivity"]
                # Convert to new format
                legacy_entry = {
                    "measurement_id": "legacy_"
                    + datetime.now().strftime("%Y%m%d_%H%M%S"),
                    "timestamp": datetime.now().isoformat(),
                    "filename": legacy_data.get("filename", "legacy_ionic.csv"),
                    "sample_height_mm": legacy_data.get("sample_height_mm"),
                    "sample_diameter_mm": legacy_data.get(
                        "sample_diameter_mm", SAMPLE_DIAMETER_MM
                    ),
                    "data": legacy_data.get("data", {}),
                    "peis_params": legacy_data.get("peis_params", {}),
                }
                existing_ionic = [legacy_entry]
            else:
                existing_ionic = []

        # Add new ionic measurement
        existing_ionic.append(ionic_entry)
        metadata_updates["ionic_conductivity_measurements"] = existing_ionic

        # Run electronic conductivity measurement if requested
        if include_electronic_conductivity and electronic_conductivity_params:
            current_measurement["message"] = (
                "Running electronic conductivity measurement..."
            )

            # Prepare electronic conductivity parameters
            electronic_params = {
                "voltages": electronic_conductivity_params.voltages,
                "durations": electronic_conductivity_params.durations,
            }

            # Perform the electronic conductivity measurement
            electronic_data = biologic_device.measure_electronic_conductivity(
                params=electronic_params
            )

            # Generate filename for electronic conductivity
            electronic_filename = f"electronic_conductivity_{sample_id}_{electronic_measurement_id}_{biologic_device.ip_address}.csv"

            # Create electronic conductivity measurement entry
            electronic_entry = {
                "measurement_id": electronic_measurement_id,
                "timestamp": measurement_timestamp,
                "filename": electronic_filename,
                "sample_height_mm": sample_height,
                "sample_diameter_mm": SAMPLE_DIAMETER_MM,
                "data": electronic_data.to_dict(orient="list"),
                "electronic_params": electronic_params,
            }

            # Get existing electronic conductivity measurements or create new list
            existing_electronic = sample.metadata.get(
                "electronic_conductivity_measurements", []
            )
            if not isinstance(existing_electronic, list):
                # Handle legacy single measurement format
                if "electronic_conductivity" in sample.metadata:
                    legacy_data = sample.metadata["electronic_conductivity"]
                    # Convert to new format
                    legacy_entry = {
                        "measurement_id": "legacy_"
                        + datetime.now().strftime("%Y%m%d_%H%M%S"),
                        "timestamp": datetime.now().isoformat(),
                        "filename": legacy_data.get(
                            "filename", "legacy_electronic.csv"
                        ),
                        "sample_height_mm": legacy_data.get("sample_height_mm"),
                        "sample_diameter_mm": legacy_data.get(
                            "sample_diameter_mm", SAMPLE_DIAMETER_MM
                        ),
                        "data": legacy_data.get("data", {}),
                        "electronic_params": legacy_data.get("electronic_params", {}),
                    }
                    existing_electronic = [legacy_entry]
                else:
                    existing_electronic = []

            # Add new electronic measurement
            existing_electronic.append(electronic_entry)
            metadata_updates["electronic_conductivity_measurements"] = (
                existing_electronic
            )

            current_measurement["progress"] = 0.3 + (2 * progress_step)

        current_measurement["progress"] = 0.9
        current_measurement["message"] = "Saving results..."

        # Update sample metadata with all measurement results
        sample_view.update_sample_metadata(sample_id_obj, metadata_updates)

        # Mark measurement as completed
        current_measurement["status"] = "completed"
        current_measurement["progress"] = 1.0
        measurements_completed = ["ionic conductivity"]
        if include_electronic_conductivity:
            measurements_completed.append("electronic conductivity")
        current_measurement["message"] = (
            f"Measurement completed successfully: {', '.join(measurements_completed)}"
        )
        current_measurement["completed_at"] = datetime.now().isoformat()

        # Store measurement IDs for reference
        current_measurement["latest_ionic_measurement_id"] = ionic_measurement_id
        if electronic_measurement_id:
            current_measurement["latest_electronic_measurement_id"] = (
                electronic_measurement_id
            )

    except Exception as e:
        current_measurement["status"] = "failed"
        current_measurement["error"] = traceback.format_exc()
        current_measurement["message"] = f"Measurement failed: {e!s}"
        current_measurement["completed_at"] = datetime.now().isoformat()


@router.post("/measure/", response_model=MeasurementResponse)
async def start_measurement(request: MeasurementRequest):
    """Start ionic conductivity measurement for a sample."""
    global current_measurement

    # Check if there's already a measurement running
    if current_measurement and current_measurement["status"] in ["queued", "running"]:
        raise HTTPException(
            status_code=409,
            detail=f"A measurement is already running for sample {current_measurement['sample_id']}",
        )

    # Validate input parameters
    if not request.sample_id.strip():
        raise HTTPException(status_code=400, detail="Sample ID cannot be empty")

    try:
        sample_id = ObjectId(request.sample_id.strip())
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Sample ID must be a valid ObjectId (24 hex characters)",
        )

    try:
        sample = sample_view.get_sample(sample_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Sample not found in the database.")

    if request.sample_height is not None and request.sample_height <= 0:
        raise HTTPException(status_code=400, detail="Sample height must be positive")

    # Validate electronic conductivity parameters if enabled
    if request.include_electronic_conductivity:
        if not request.electronic_conductivity_params:
            raise HTTPException(
                status_code=400,
                detail="Electronic conductivity parameters are required when electronic conductivity is enabled",
            )

        params = request.electronic_conductivity_params
        if not params.voltages or not params.durations:
            raise HTTPException(
                status_code=400, detail="Voltages and durations lists cannot be empty"
            )

        if len(params.voltages) != len(params.durations):
            raise HTTPException(
                status_code=400,
                detail="Voltages and durations lists must have the same length",
            )

        if any(d <= 0 for d in params.durations):
            raise HTTPException(
                status_code=400, detail="All durations must be positive"
            )

    # Create the current measurement
    created_at = datetime.now().isoformat()
    sample_name = get_sample_name(request.sample_id.strip())
    current_measurement = {
        "sample_id": request.sample_id.strip(),
        "sample_name": sample_name,
        "sample_height": request.sample_height,
        "peis_params": request.peis_params.model_dump(),
        "include_electronic_conductivity": request.include_electronic_conductivity,
        "electronic_conductivity_params": (
            request.electronic_conductivity_params.model_dump()
            if request.electronic_conductivity_params
            else None
        ),
        "status": "queued",
        "message": "Measurement queued",
        "created_at": created_at,
        "started_at": None,
        "completed_at": None,
        "error": None,
        "progress": 0.0,
    }

    # Start the measurement in a background thread
    thread = threading.Thread(
        target=run_measurement,
        args=(
            request.sample_id.strip(),
            request.sample_height,
            request.peis_params,
            request.include_electronic_conductivity,
            request.electronic_conductivity_params,
        ),
    )
    thread.daemon = True
    thread.start()

    return MeasurementResponse(
        sample_id=request.sample_id.strip(),
        sample_height=request.sample_height,
        peis_params=request.peis_params,
        include_electronic_conductivity=request.include_electronic_conductivity,
        electronic_conductivity_params=request.electronic_conductivity_params,
        status="queued",
        message="Measurement started successfully",
    )


@router.get("/status/")
async def get_measurement_status():
    """Get the status of the current measurement."""
    if not current_measurement:
        return {}

    return MeasurementStatus(**current_measurement)


@router.get("/measurements/{sample_id}/", response_model=MeasurementListResponse)
async def get_sample_measurements(sample_id: str):
    """Get all measurements for a specific sample."""
    try:
        sample_id_obj = ObjectId(sample_id.strip())
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Sample ID must be a valid ObjectId (24 hex characters)",
        )

    try:
        sample = sample_view.get_sample(sample_id_obj)
    except Exception:
        raise HTTPException(status_code=400, detail="Sample not found in the database.")

    # Get ionic conductivity measurements
    ionic_measurements = sample.metadata.get("ionic_conductivity_measurements", [])
    # Handle legacy format
    if not ionic_measurements and "ionic_conductivity" in sample.metadata:
        legacy_data = sample.metadata["ionic_conductivity"]
        ionic_measurements = [
            {
                "measurement_id": "legacy_ionic",
                "timestamp": datetime.now().isoformat(),
                "filename": legacy_data.get("filename", "legacy_ionic.csv"),
                "sample_height_mm": legacy_data.get("sample_height_mm"),
                "sample_diameter_mm": legacy_data.get(
                    "sample_diameter_mm", SAMPLE_DIAMETER_MM
                ),
                "data": legacy_data.get("data", {}),
                "peis_params": legacy_data.get("peis_params", {}),
            }
        ]

    # Get electronic conductivity measurements
    electronic_measurements = sample.metadata.get(
        "electronic_conductivity_measurements", []
    )
    # Handle legacy format
    if not electronic_measurements and "electronic_conductivity" in sample.metadata:
        legacy_data = sample.metadata["electronic_conductivity"]
        electronic_measurements = [
            {
                "measurement_id": "legacy_electronic",
                "timestamp": datetime.now().isoformat(),
                "filename": legacy_data.get("filename", "legacy_electronic.csv"),
                "sample_height_mm": legacy_data.get("sample_height_mm"),
                "sample_diameter_mm": legacy_data.get(
                    "sample_diameter_mm", SAMPLE_DIAMETER_MM
                ),
                "data": legacy_data.get("data", {}),
                "electronic_params": legacy_data.get("electronic_params", {}),
            }
        ]

    # Convert to MeasurementEntry objects
    ionic_entries = [MeasurementEntry(**entry) for entry in ionic_measurements]
    electronic_entries = [
        MeasurementEntry(**entry) for entry in electronic_measurements
    ]

    return MeasurementListResponse(
        sample_id=sample_id.strip(),
        ionic_conductivity_measurements=ionic_entries,
        electronic_conductivity_measurements=electronic_entries,
    )


@router.get("/plot/ionic/{sample_id}/{measurement_id}/", response_model=PlotData)
async def get_ionic_plot_data(sample_id: str, measurement_id: str):
    """Get plot data for a specific ionic conductivity measurement."""
    try:
        sample_id_obj = ObjectId(sample_id.strip())
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Sample ID must be a valid ObjectId (24 hex characters)",
        )

    try:
        sample = sample_view.get_sample(sample_id_obj)
    except Exception:
        raise HTTPException(status_code=400, detail="Sample not found in the database.")

    # Get ionic conductivity measurements
    ionic_measurements = sample.metadata.get("ionic_conductivity_measurements", [])

    # Handle legacy format
    if (
        not ionic_measurements
        and "ionic_conductivity" in sample.metadata
        and measurement_id == "legacy_ionic"
    ):
        legacy_data = sample.metadata["ionic_conductivity"]
        measurement_data = pd.DataFrame(legacy_data.get("data", {}))
    else:
        # Find the specific measurement
        measurement_data = None
        for measurement in ionic_measurements:
            if measurement["measurement_id"] == measurement_id:
                measurement_data = pd.DataFrame(measurement["data"])
                break

        if measurement_data is None:
            raise HTTPException(
                status_code=404, detail="Ionic conductivity measurement not found"
            )

    if measurement_data.empty:
        raise HTTPException(
            status_code=404, detail="No measurement data found for this measurement"
        )

    try:
        # Generate plot data using the BioLogic device's plot function
        plot_data = biologic_device.plot_ionic_conductivity(measurement_data)
        return PlotData(**plot_data)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate plot data: {e!s}"
        )


@router.get("/plot/electronic/{sample_id}/{measurement_id}/", response_model=PlotData)
async def get_electronic_plot_data(sample_id: str, measurement_id: str):
    """Get plot data for a specific electronic conductivity measurement."""
    try:
        sample_id_obj = ObjectId(sample_id.strip())
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Sample ID must be a valid ObjectId (24 hex characters)",
        )

    try:
        sample = sample_view.get_sample(sample_id_obj)
    except Exception:
        raise HTTPException(status_code=400, detail="Sample not found in the database.")

    # Get electronic conductivity measurements
    electronic_measurements = sample.metadata.get(
        "electronic_conductivity_measurements", []
    )

    # Handle legacy format
    if (
        not electronic_measurements
        and "electronic_conductivity" in sample.metadata
        and measurement_id == "legacy_electronic"
    ):
        legacy_data = sample.metadata["electronic_conductivity"]
        measurement_data = pd.DataFrame(legacy_data.get("data", {}))
    else:
        # Find the specific measurement
        measurement_data = None
        for measurement in electronic_measurements:
            if measurement["measurement_id"] == measurement_id:
                measurement_data = pd.DataFrame(measurement["data"])
                break

        if measurement_data is None:
            raise HTTPException(
                status_code=404, detail="Electronic conductivity measurement not found"
            )

    if measurement_data.empty:
        raise HTTPException(
            status_code=404,
            detail="No electronic measurement data found for this measurement",
        )

    try:
        # Generate plot data using the BioLogic device's plot function
        plot_data = biologic_device.plot_electronic_conductivity(measurement_data)
        return PlotData(**plot_data)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate electronic plot data: {e!s}"
        )


# Keep old endpoints for backward compatibility - use latest measurement
@router.get("/plot/ionic/{sample_id}/", response_model=PlotData)
async def get_ionic_plot_data_legacy(sample_id: str):
    """Get plot data for latest ionic conductivity measurement (backward compatibility)."""
    # Get all measurements first
    measurements_response = await get_sample_measurements(sample_id)

    if not measurements_response.ionic_conductivity_measurements:
        raise HTTPException(
            status_code=404, detail="No ionic conductivity data found for this sample"
        )

    # Use the latest measurement (last in list)
    latest_measurement = measurements_response.ionic_conductivity_measurements[-1]
    return await get_ionic_plot_data(sample_id, latest_measurement.measurement_id)


@router.get("/plot/electronic/{sample_id}/", response_model=PlotData)
async def get_electronic_plot_data_legacy(sample_id: str):
    """Get plot data for latest electronic conductivity measurement (backward compatibility)."""
    # Get all measurements first
    measurements_response = await get_sample_measurements(sample_id)

    if not measurements_response.electronic_conductivity_measurements:
        raise HTTPException(
            status_code=404,
            detail="No electronic conductivity data found for this sample",
        )

    # Use the latest measurement (last in list)
    latest_measurement = measurements_response.electronic_conductivity_measurements[-1]
    return await get_electronic_plot_data(sample_id, latest_measurement.measurement_id)


# Keep the old endpoint for backward compatibility
@router.get("/plot/{sample_id}/", response_model=PlotData)
async def get_plot_data(sample_id: str):
    """Get plot data for latest ionic conductivity measurement (backward compatibility)."""
    return await get_ionic_plot_data_legacy(sample_id)


@router.delete("/measurement/")
async def clear_measurement():
    """Clear the current measurement (only if completed or failed)."""
    global current_measurement

    if not current_measurement:
        raise HTTPException(status_code=404, detail="No measurement found")

    if current_measurement["status"] in ["running", "queued"]:
        raise HTTPException(
            status_code=400, detail="Cannot clear a running measurement"
        )

    current_measurement = None
    return {"message": "Measurement cleared successfully"}


@router.get("/defaults/", response_model=DefaultParametersResponse)
async def get_default_parameters():
    """Get default measurement parameters."""
    # Extract voltages from DEFAULT_CA_PARAMS (handling potential typo "voltags")
    default_voltages = DEFAULT_CA_PARAMS.get(
        "voltags", DEFAULT_CA_PARAMS.get("voltages", [0.5])
    )
    default_durations = DEFAULT_CA_PARAMS.get("duration", [600])

    return DefaultParametersResponse(
        peis_params=PeisParams(
            initial_frequency=DEFAULT_PEIS_PARAMS["initial_frequency"],
            final_frequency=DEFAULT_PEIS_PARAMS["final_frequency"],
            frequency_number=DEFAULT_PEIS_PARAMS["frequency_number"],
            repeat=DEFAULT_PEIS_PARAMS["repeat"],
        ),
        electronic_conductivity_params=ElectronicConductivityParams(
            voltages=default_voltages,
            durations=default_durations,
        ),
    )


@router.patch("/sample-height/", response_model=MeasurementStatus)
async def update_sample_height(request: UpdateSampleHeightRequest):
    """Update the sample height for the current measurement."""
    global current_measurement
    try:
        float(request.sample_height)
    except ValueError:
        raise HTTPException(status_code=400, detail="Sample height must be a number")

    if not current_measurement:
        raise HTTPException(status_code=404, detail="No active measurement found")

    if current_measurement["status"] == "running":
        raise HTTPException(
            status_code=400,
            detail="Cannot update sample height while measurement is running",
        )

    if request.sample_height <= 0:
        raise HTTPException(status_code=400, detail="Sample height must be positive")

    # Update the sample height
    current_measurement["sample_height"] = request.sample_height

    # Update the database if the measurement is completed
    if current_measurement["status"] == "completed":
        try:
            sample_id = current_measurement["sample_id"]
            sample_id_obj = ObjectId(sample_id)
            sample = sample_view.get_sample(sample_id_obj)

            updates = {}

            # Update ionic measurement if available
            if "latest_ionic_measurement_id" in current_measurement:
                ionic_measurements = sample.metadata.get(
                    "ionic_conductivity_measurements", []
                )
                for measurement in ionic_measurements:
                    if (
                        measurement["measurement_id"]
                        == current_measurement["latest_ionic_measurement_id"]
                    ):
                        measurement["sample_height_mm"] = request.sample_height
                        break
                updates["ionic_conductivity_measurements"] = ionic_measurements

            # Update electronic measurement if available
            if "latest_electronic_measurement_id" in current_measurement:
                electronic_measurements = sample.metadata.get(
                    "electronic_conductivity_measurements", []
                )
                for measurement in electronic_measurements:
                    if (
                        measurement["measurement_id"]
                        == current_measurement["latest_electronic_measurement_id"]
                    ):
                        measurement["sample_height_mm"] = request.sample_height
                        break
                updates["electronic_conductivity_measurements"] = (
                    electronic_measurements
                )

            if updates:
                sample_view.update_sample_metadata(sample_id_obj, updates)
                print(
                    f"Successfully updated sample height in database for sample {sample_id}"
                )

        except Exception as e:
            # Log the error but don't fail the request since we updated the current measurement
            print(f"Warning: Failed to update database with new sample height: {e}")

    return MeasurementStatus(**current_measurement)


@router.post("/load-sample/", response_model=MeasurementStatus)
async def load_sample(request: LoadSampleRequest):
    """Load an existing sample's conductivity measurement into current measurement."""
    global current_measurement

    # Validate sample ID
    try:
        sample_id_obj = ObjectId(request.sample_id.strip())
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Sample ID must be a valid ObjectId (24 hex characters)",
        )

    try:
        sample = sample_view.get_sample(sample_id_obj)
    except Exception:
        raise HTTPException(status_code=400, detail="Sample not found in the database.")

    # Get measurements
    measurements_response = await get_sample_measurements(request.sample_id.strip())

    if (
        not measurements_response.ionic_conductivity_measurements
        and not measurements_response.electronic_conductivity_measurements
    ):
        raise HTTPException(
            status_code=404, detail="No conductivity data found for this sample"
        )

    # Determine which measurements to load
    ionic_measurement = None
    electronic_measurement = None

    if request.ionic_measurement_id:
        # Find specific ionic measurement
        for measurement in measurements_response.ionic_conductivity_measurements:
            if measurement.measurement_id == request.ionic_measurement_id:
                ionic_measurement = measurement
                break
        if not ionic_measurement:
            raise HTTPException(
                status_code=404, detail="Specified ionic measurement not found"
            )
    elif measurements_response.ionic_conductivity_measurements:
        # Use latest ionic measurement
        ionic_measurement = measurements_response.ionic_conductivity_measurements[-1]

    if request.electronic_measurement_id:
        # Find specific electronic measurement
        for measurement in measurements_response.electronic_conductivity_measurements:
            if measurement.measurement_id == request.electronic_measurement_id:
                electronic_measurement = measurement
                break
        if not electronic_measurement:
            raise HTTPException(
                status_code=404, detail="Specified electronic measurement not found"
            )
    elif measurements_response.electronic_conductivity_measurements:
        # Use latest electronic measurement
        electronic_measurement = (
            measurements_response.electronic_conductivity_measurements[-1]
        )

    # Reconstruct measurement parameters
    sample_height = None
    peis_params = None
    electronic_params = None

    if ionic_measurement:
        sample_height = ionic_measurement.sample_height_mm
        peis_params = ionic_measurement.peis_params or DEFAULT_PEIS_PARAMS.copy()

    if electronic_measurement:
        if sample_height is None:
            sample_height = electronic_measurement.sample_height_mm
        electronic_params = electronic_measurement.electronic_params or {}

    # Use default PEIS params if not available
    if peis_params is None:
        peis_params = DEFAULT_PEIS_PARAMS.copy()

    # Create measurement types message
    measurement_types = []
    if ionic_measurement:
        measurement_types.append("ionic conductivity")
    if electronic_measurement:
        measurement_types.append("electronic conductivity")

    sample_name = get_sample_name(request.sample_id.strip())

    current_measurement = {
        "sample_id": request.sample_id.strip(),
        "sample_name": sample_name,
        "sample_height": sample_height,
        "peis_params": peis_params,
        "include_electronic_conductivity": electronic_measurement is not None,
        "electronic_conductivity_params": electronic_params,
        "status": "completed",
        "message": f"Loaded existing measurement: {', '.join(measurement_types)}",
        "created_at": datetime.now().isoformat(),
        "started_at": datetime.now().isoformat(),
        "completed_at": datetime.now().isoformat(),
        "error": None,
        "progress": 1.0,
        "loaded_ionic_measurement_id": (
            ionic_measurement.measurement_id if ionic_measurement else None
        ),
        "loaded_electronic_measurement_id": (
            electronic_measurement.measurement_id if electronic_measurement else None
        ),
    }

    return MeasurementStatus(**current_measurement)
