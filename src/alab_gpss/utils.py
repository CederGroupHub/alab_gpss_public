from abc import ABC

from alab_management import BaseTask, Sample

NO_ALIVE_SAMPLE_MSG = (
    "No samples are alive in the lab view. "
    "Assuming the associated samples have been removed from the lab "
    "due to cancellation or failure of the task."
)


class GPSSBaseTask(BaseTask, ABC):
    """Base class for all GPSS tasks."""

    def check_if_samples_alive(self):
        """
        Check if the samples are still alive in the lab view.
        If not, remove them from the samples list.
        """
        samples = []

        for sample in self.samples:
            sample_obj: Sample = self.lab_view.get_sample(sample)
            if sample_obj.position is not None:
                samples.append(sample)

        if not samples:
            self.set_message("No samples are alive in the lab view.")
            return NO_ALIVE_SAMPLE_MSG
        return None
