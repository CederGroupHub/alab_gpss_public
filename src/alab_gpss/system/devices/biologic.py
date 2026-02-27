"""BioLogic device class for handling BioLogic devices."""

import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from alab_management import mock

try:
    from easy_biologic import BiologicDevice
    from easy_biologic.base_programs import CA, PEIS
    from easy_biologic.lib.ec_lib import IRange
except OSError:
    warnings.warn("easy_biologic is not installed on this system.")
    BiologicDevice = None
    PEIS = None
    CA = None
    IRange = None


DEFAULT_PEIS_PARAMS = {
    "voltage": 0,
    "final_frequency": 1,
    "initial_frequency": 7e6,
    "amplitude_voltage": 0.01,  # 10 mV
    "frequency_number": 60,
    "duration": 0,
    "repeat": 2,
    "wait": 0.1,
}

DEFAULT_CA_PARAMS = {
    "voltages": [0.5],
    "durations": [600],  # 10 minutes
    "time_interval": 200e-6,  # 200 microseconds
    "current_interval": 0,
    # "current_range": IRange.AUTO if IRange is not None else 12,
}


def average_every_m_seconds(df: pd.DataFrame, m: int) -> pd.DataFrame:
    """
    Compute time-weighted average over every `m` seconds using np.trapz integration.

    Parameters:
    - df (pd.DataFrame): Input DataFrame with a "Time [s]" column.
    - m (int): Time interval in seconds over which to average.

    Returns:
    - pd.DataFrame: A new DataFrame with time-weighted averages over each M-second interval.
    """
    if "Time [s]" not in df.columns:
        raise ValueError("DataFrame must contain a 'Time [s]' column.")

    df = df.copy()
    df = df.sort_values("Time [s]")  # Ensure time is sorted
    df["TimeBin"] = (df["Time [s]"] // m) * m

    result = []

    numeric_cols = df.select_dtypes(include=[np.number]).columns.drop("Time [s]")

    for time_bin, group in df.groupby("TimeBin"):
        time_vals = group["Time [s]"].to_numpy()
        row = {"Time [s]": time_bin}
        dt = time_vals[-1] - time_vals[0]
        if dt == 0:
            # If all time values are the same, fallback to simple mean
            for col in numeric_cols:
                row[col] = group[col].mean()
        else:
            for col in numeric_cols:
                y_vals = group[col].to_numpy()
                row[col] = np.trapz(y_vals, time_vals) / dt
        result.append(row)

    return pd.DataFrame(result)


class BioLogic:
    """
    BioLogic device class for handling BioLogic devices.

    Using easy_biologic for communication with BioLogic devices.
    """

    description: str = (
        "BioLogic device for electrochemical experiments. Communicates with BioLogic devices using easy_biologic."
    )

    def __init__(self, ip_address: str, data_folder: str | Path) -> None:
        self.ip_address = ip_address
        self.data_folder = Path(data_folder)
        self.driver: BiologicDevice | None = None

        if not self.data_folder.exists():
            self.data_folder.mkdir(parents=True, exist_ok=True)
        elif not self.data_folder.is_dir():
            raise ValueError(f"Data folder {self.data_folder} is not a directory.")

        self.__is_running = False

    def is_running(self) -> bool:
        if self.driver is None:
            return False
        return self.__is_running

    @mock(object_type=BiologicDevice)
    def get_driver(self):
        """
        Get the BioLogic device driver.

        Returns:
            An instance of the BioLogic device driver.
        """
        self.driver = BiologicDevice(address=self.ip_address)
        return self.driver

    def connect(self):
        """
        Connect to the BioLogic device.
        """
        if self.driver is None:
            self.driver = self.get_driver()

    def disconnect(self):
        """
        Disconnect from the BioLogic device.
        """
        if self.driver is not None:
            if self.driver.is_connected():
                self.driver.disconnect()
            self.driver = None

    @mock(
        return_constant=pd.read_csv(
            Path(__file__).parent / "example_data" / "peis 1.csv", skiprows=1
        )
    )
    def measure_ionic_conductivity(
        self, params: dict[str, Any] | None = None, channel: int = 0
    ):
        """
        Assuming the sample has been loaded to the device
        """
        if self.driver is None:
            raise RuntimeError("Device not connected.")

        if params is None:
            params = DEFAULT_PEIS_PARAMS

        running_params = DEFAULT_PEIS_PARAMS.copy()
        running_params.update(params)

        program = PEIS(
            self.driver,
            params=running_params,
            channels=[channel],
        )
        self.__is_running = True
        filename = (
            f"PEIS_{self.driver.address}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        file_path = self.data_folder / filename
        program.run(retrieve_data=True)
        program.save_data(file_path)
        self.__is_running = False

        data = pd.read_csv(file_path, skiprows=1)
        return data

    @staticmethod
    def plot_ionic_conductivity(data: pd.DataFrame):
        """
        Plot the ionic conductivity data as Nyquist plot (ReIm vs ImRe).

        Args:
            data: The DataFrame containing the ionic conductivity data.

        Returns:
            dict: Plot data in Plotly JSON format
        """
        if not isinstance(data, pd.DataFrame):
            raise ValueError("Data must be a pandas DataFrame.")

        import numpy as np

        # Calculate ReIm and ImRe from impedance modulus and phase
        data["ReIm"] = data["Impedance modulus"] * np.cos(data["Impedance phase"])
        data["ImRe"] = -data["Impedance modulus"] * np.sin(data["Impedance phase"])
        data["log_frequency"] = np.log10(data["Frequency [Hz]"])
        # Create Plotly JSON format
        plotly_data = {
            "data": [
                {
                    "x": data["ReIm"].tolist(),
                    "y": data["ImRe"].tolist(),
                    "mode": "markers",
                    "type": "scatter",
                    "marker": {
                        "size": 8,
                        "color": data["log_frequency"].tolist(),
                        "colorscale": "Viridis",
                        "colorbar": {
                            "title": "log₁₀(Frequency [Hz])",
                            "titleside": "right",
                        },
                        "showscale": True,
                    },
                    "text": [f"Freq: {freq:.2e} Hz" for freq in data["Frequency [Hz]"]],
                    "hovertemplate": "ReIm: %{x:.2f} Ω<br>ImRe: %{y:.2f} Ω<br>%{text}<extra></extra>",
                    "name": "Impedance Data",
                }
            ],
            "layout": {
                "title": {"text": "Nyquist Plot - Ionic Conductivity", "x": 0.5},
                "xaxis": {"title": "ReIm (Ω)", "showgrid": True, "zeroline": True},
                "yaxis": {"title": "ImRe (Ω)", "showgrid": True, "zeroline": True},
                "hovermode": "closest",
                "showlegend": False,
                "plot_bgcolor": "white",
                "paper_bgcolor": "white",
            },
        }

        return plotly_data

    @mock(
        return_constant=pd.read_csv(
            Path(__file__).parent / "example_data" / "ca.csv", skiprows=0
        )
    )
    def measure_electronic_conductivity(
        self,
        params: dict[str, Any] | None = None,
        channel: int = 0,
        average: bool = True,
    ):
        """
        Measure electronic conductivity using the BioLogic device.

        Args:
            params: Parameters for the measurement.
            channel: The channel to use for the measurement.
            average: Whether to average the data every n rows.

        Returns:
            DataFrame containing the measurement data.
        """
        if self.driver is None:
            raise RuntimeError("Device not connected.")

        if params is None:
            params = DEFAULT_CA_PARAMS

        running_params = DEFAULT_CA_PARAMS.copy()
        running_params.update(params)

        program = CA(
            self.driver,
            params=running_params,
            channels=[channel],
        )
        self.__is_running = True
        filename = (
            f"CA_{self.driver.address}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        file_path = self.data_folder / filename
        program.run(retrieve_data=True)
        program.save_data(file_path)
        self.__is_running = False

        data = pd.read_csv(file_path, skiprows=1)
        if average:
            data = average_every_m_seconds(data, 1)
        return data

    @staticmethod
    def plot_electronic_conductivity(data: pd.DataFrame):
        """
        Plot the electronic conductivity data as a simple line plot.

        Args:
            data: The DataFrame containing the electronic conductivity data.

        Returns:
            dict: Plot data in Plotly JSON format
        """
        if not isinstance(data, pd.DataFrame):
            raise ValueError("Data must be a pandas DataFrame.")

        # Create Plotly JSON format
        plotly_data = {
            "data": [
                {
                    "x": data["Time [s]"].tolist(),
                    "y": data["Current [A]"].tolist(),
                    "mode": "lines+markers",
                    "type": "scatter",
                    "name": "Current vs Time",
                }
            ],
            "layout": {
                "title": {"text": "Electronic Conductivity Measurement", "x": 0.5},
                "xaxis": {"title": "Time [s]", "showgrid": True, "zeroline": True},
                "yaxis": {"title": "Current [A]", "showgrid": True, "zeroline": True},
                "hovermode": "closest",
                "showlegend": False,
                "plot_bgcolor": "white",
                "paper_bgcolor": "white",
            },
        }

        return plotly_data
