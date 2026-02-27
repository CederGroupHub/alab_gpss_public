"""Device class for the REINER jetStamp 1025 injket printer used for labeling filled vials."""

from typing import ClassVar

from alab_control.dymo_labelwriter.dymo_labelwriter import DYMOLabelWriter
from alab_management import BaseDevice, mock
from bson import ObjectId


class LabelPrinter(BaseDevice):
    """A device for labeling filled vials."""

    description: ClassVar[str] = (
        "A DYMO LabelWriter Wireless printer for labeling filled vials with QR code and name."
    )

    def __init__(self, printer_name, sumatra_pdf_path, *args, **kwargs):
        """Initialize the VialLabeler object."""
        super().__init__(*args, **kwargs)
        self.printer_name = printer_name
        self.sumatra_pdf_path = sumatra_pdf_path
        self.driver: DYMOLabelWriter | None = None

    @mock(object_type=DYMOLabelWriter)
    def get_driver(self):
        """Get the driver for the printer."""
        self.driver = DYMOLabelWriter(self.printer_name, self.sumatra_pdf_path)
        return self.driver

    def connect(self):
        """Connect to device."""
        self.driver = self.get_driver()

    def disconnect(self):
        """Disconnect from device."""
        if self.driver is not None:
            self.driver = None

    def is_running(self) -> bool:
        """Check if device is running."""
        return False

    @property
    def sample_positions(self):
        """Return the sample positions of the vial labeler."""
        return []

    def print_label(
        self,
        sample_id: ObjectId | str,
        sample_name: str,
        consumable_rack_level: int,
        consumable_rack_row: int,
    ):
        """Print a label for the given sample ID."""
        self.driver.print_label(
            sample_id=ObjectId(sample_id),
            sample_name=sample_name,
            consumable_rack_level=consumable_rack_level,
            consumable_rack_row=consumable_rack_row,
        )
