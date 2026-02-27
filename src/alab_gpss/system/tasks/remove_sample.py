from alab_gpss.system import ConsumableRack, LabelPrinter
from alab_gpss.utils import GPSSBaseTask


class RemoveSample(GPSSBaseTask):
    def __init__(self, print_label: bool = True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.print_label = print_label

    def validate(self) -> bool:
        if len(self.samples) != 1:
            return False
        return True

    def run(self):
        if msg := GPSSBaseTask.check_if_samples_alive(self):
            return msg

        sample = self.samples[0]
        with self.lab_view.request_resources({"gpss/consumable_rack": {}}) as (
            devices,
            _,
        ):
            consumable_rack: ConsumableRack = devices["gpss/consumable_rack"]
            assigned_level, assigned_row = consumable_rack.get_sample_slot(
                self.lab_view.get_sample(sample).sample_id
            )
            consumable_rack.mark_slot_as_dirty(
                self.lab_view.get_sample(sample).sample_id
            )

        if self.print_label:
            with self.lab_view.request_resources({"gpss/label_printer": {}}) as (
                devices,
                _,
            ):
                label_printer: LabelPrinter = devices["gpss/label_printer"]

                self.set_message("Printing label.")
                sample_obj = self.lab_view.get_sample(sample)

                label_printer.print_label(
                    str(sample_obj.sample_id),
                    sample_obj.name,
                    assigned_level,
                    assigned_row,
                )

        self.set_message(
            f"Waiting for cleaning up consumable rack level: {assigned_level}, row: {assigned_row}"
        )
