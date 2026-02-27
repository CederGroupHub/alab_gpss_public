from __future__ import annotations

import time
from traceback import format_exc

from alab_control.mt_auto_balance.auto_balance import (
    BalanceWeightResult,
    MTAutoBalance,
)
from alab_control.mt_auto_balance.balance_restarter import BalanceRestarter
from alab_management.device_view import BaseDevice
from alab_management.device_view.device import mock
from alab_management.sample_view import SamplePosition
from requests import ConnectTimeout, ReadTimeout


class AutoBalance(BaseDevice):
    """A device for the auto balance. It is used for weighing samples."""

    description = "Auto balance for powder dispensing."

    def __init__(
        self,
        ip_address,
        balance_restarter_ip_address: str | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.ip_address = ip_address
        self.balance_restarter_ip_address = balance_restarter_ip_address
        self.driver: MTAutoBalance | None = None
        self.balance_restarter_driver: BalanceRestarter | None = None
        self.running = False

    @mock(object_type=[MTAutoBalance, BalanceRestarter])
    def get_driver(self):
        self.driver = MTAutoBalance(host=f"http://{self.ip_address}:81")
        if self.balance_restarter_ip_address is not None:
            self.balance_restarter_driver = BalanceRestarter(
                self.balance_restarter_ip_address
            )
        return self.driver, self.balance_restarter_driver

    def connect(self):
        self.driver, self.balance_restarter_driver = self.get_driver()

    def disconnect(self):
        self.driver = None
        self.balance_restarter_driver = None

    @property
    def sample_positions(self):
        return [
            SamplePosition(
                "crucible",
                description="The position inside the auto balance to hold the crucible.",
            ),
            SamplePosition(
                "dosing_head",
                description="The position on top of the auto balance to hold the dosing head.",
            ),
        ]

    def restart_balance(self):
        if self.balance_restarter_ip_address is None:
            return  # No restarter configured

        self.balance_restarter_driver.restart_balance(block=True)
        self.set_message(
            "The balance has been restarted. Waiting for 60 seconds to complete restart."
        )
        start_time = time.time()
        time.sleep(120)
        while time.time() < start_time + 300:  # wait up to 5 minutes
            self.set_message(
                "Waiting for the balance to come back online. Elapsed time: "
                + str(int(time.time() - start_time))
                + " seconds."
            )
            try:
                self.driver.get_weight("Immediate")
            except (ConnectTimeout, ReadTimeout):
                time.sleep(5)
                continue
            break
        else:
            raise RuntimeError("The balance did not come back online in time.")
        self.set_message("The balance has been restarted.")

    def open_door(self):
        self.set_message("The door of the auto balance is opening.")
        restart_counter = 0
        while True:
            try:
                self.driver.open_door(door="LeftOuter")
                break
            except Exception as e:
                if (
                    self.balance_restarter_ip_address is not None
                    and restart_counter < 3
                    and (
                        isinstance(e, (ConnectTimeout, ReadTimeout))
                        or "SessionService failed" in str(e)
                        or "SpectraTimeoutException" in str(e)
                        or "DraftShieldsService failed" in str(e)
                    )
                ):
                    restart_counter += 1
                    try:
                        self.restart_balance()
                    except Exception as e:
                        self.set_message(
                            "Restarting the balance failed. The error is: "
                            + str(e)
                            + "."
                        )
                        response = self.request_maintenance(
                            "Restarting the balance failed. Please check the balance. The error is "
                            + format_exc(),
                            options=["Retry", "Cancel"],
                        )
                        if response == "Cancel":
                            raise
                    continue
                response = self.request_maintenance(
                    "Opening the left door of the auto balance failed. "
                    "Please check the balance. The error is " + format_exc(),
                    options=["Retry", "Cancel"],
                )
                if response == "Cancel":
                    raise
                continue
        self.set_message("The door of the auto balance is opened.")

    def close_door(self):
        self.set_message("The door of the auto balance is closing.")
        restart_counter = 0
        while True:
            try:
                self.driver.close_door(door="LeftOuter")
                break
            except Exception as e:
                if (
                    self.balance_restarter_ip_address is not None
                    and restart_counter < 3
                    and (
                        isinstance(e, (ConnectTimeout, ReadTimeout))
                        or "SessionService failed" in str(e)
                        or "SpectraTimeoutException" in str(e)
                        or "DraftShieldsService failed" in str(e)
                    )
                ):
                    restart_counter += 1
                    try:
                        self.restart_balance()
                    except Exception as e:
                        self.set_message(
                            "Restarting the balance failed. The error is: "
                            + str(e)
                            + "."
                        )
                        response = self.request_maintenance(
                            "Restarting the balance failed. Please check the balance. The error is "
                            + format_exc(),
                            options=["Retry", "Cancel"],
                        )
                        if response == "Cancel":
                            raise
                    continue
                response = self.request_maintenance(
                    "Closing the left door of the auto balance failed. "
                    "Please check the balance. The error is " + format_exc(),
                    options=["Retry", "Cancel"],
                )
                if response == "Cancel":
                    raise
        self.set_message("The door of the auto balance is closed.")

    def zero(self):
        restart_counter = 0
        while True:
            self.set_message("Zeroing the balance.")
            try:
                self.driver.zero()
                self.set_message("The balance is zeroed.")
                break
            except Exception as e:
                if (
                    self.balance_restarter_ip_address is not None
                    and restart_counter < 3
                    and (
                        isinstance(e, (ConnectTimeout, ReadTimeout))
                        or "SessionService failed" in str(e)
                        or "SpectraTimeoutException" in str(e)
                        or "DraftShieldsService failed" in str(e)
                    )
                ):
                    restart_counter += 1
                    try:
                        self.restart_balance()
                    except Exception as e:
                        self.set_message(
                            "Restarting the balance failed. The error is: "
                            + str(e)
                            + "."
                        )
                        response = self.request_maintenance(
                            "Restarting the balance failed. Please check the balance. The error is "
                            + format_exc(),
                            options=["Retry", "Cancel"],
                        )
                        if response == "Cancel":
                            raise
                    continue
                response = self.request_maintenance(
                    "Zeroing the balance failed. Please check the balance. The error is "
                    + format_exc(),
                    options=["Retry", "Cancel"],
                )
                if response == "Cancel":
                    raise

    @mock(return_constant=(0.0, None))
    def automatic_dosing(
        self,
        target_value_g: float,
        lower_tolerance_percent: float,
        upper_tolerance_percent: float,
    ) -> tuple[float, str | None]:
        self.running = True
        try:
            self.set_message(
                f"Starting automatic dosing, target amount is {target_value_g}g, "
                f"lower tolerance is {lower_tolerance_percent}%, "
                f"upper tolerance is {upper_tolerance_percent}%."
            )

            restart_counter = 0
            while True:
                try:
                    for i in range(5):
                        result = self.driver.automatic_dosing(
                            target_value_g=target_value_g,
                            lower_tolerance_percent=lower_tolerance_percent,
                            upper_tolerance_percent=upper_tolerance_percent,
                        )
                        if (
                            result["success"]
                            or result["error"] != "TareUnderload"
                            or result["error"] != "TareNegativeGrossWeight"
                        ):
                            break
                        self.set_message(
                            "Experience an error: " + result["error"] + ". Retrying..."
                        )
                except Exception as e:
                    if (
                        self.balance_restarter_ip_address is not None
                        and restart_counter < 3
                        and (
                            isinstance(e, (ConnectTimeout, ReadTimeout))
                            or "SessionService failed" in str(e)
                            or "SpectraTimeoutException" in str(e)
                            or "DraftShieldsService failed" in str(e)
                        )
                    ):
                        restart_counter += 1
                        try:
                            self.restart_balance()
                        except Exception as e:
                            self.set_message(
                                "Restarting the balance failed. The error is: "
                                + str(e)
                                + "."
                            )
                            response = self.request_maintenance(
                                "Restarting the balance failed. Please check the balance. The error is "
                                + format_exc(),
                                options=["Retry", "Cancel"],
                            )
                            if response == "Cancel":
                                raise
                        continue
                    response = self.request_maintenance(
                        "Automatic dosing failed. Please check the balance. The error is "
                        + format_exc(),
                        options=["Retry", "Cancel"],
                    )
                    if response == "Cancel":
                        raise
                    continue
                break

            self.set_message("Automatic dosing finished. The result is: " + str(result))
            weighing_result: BalanceWeightResult | None = result["result"]
            if weighing_result is None:
                delta_weight = 0.0
            else:
                delta_weight = weighing_result.NetWeight.get_weight_gram()

            if result["success"]:
                return delta_weight, None
            return delta_weight, result["error"]
        finally:
            self.running = False
            self.set_message("")

    def is_running(self) -> bool:
        return self.running
