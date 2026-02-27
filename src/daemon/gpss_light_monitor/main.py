import os
import requests
from pydantic import BaseModel, Field
from typing import Any, Literal
import uuid
import logging
import traceback
import time


class Device(BaseModel):
    id: str = Field(alias="device")
    sku: str
    capabilities: list[dict[str, Any]]
    name: str = Field(alias="deviceName")


class GoveeClient:
    def __init__(
        self, api_key: str = None, base_url: str = "https://openapi.api.govee.com"
    ):
        self.api_key = api_key if api_key else os.getenv("GOOVE_API_KEY")
        self.base_url = base_url

    @property
    def devices(self):
        response = requests.get(
            f"{self.base_url}/router/api/v1/user/devices",
            headers={"Content-Type": "application/json", "Govee-API-Key": self.api_key},
        )
        response_json = response.json()
        if response.status_code != 200 and response_json["message"] != "success":
            raise Exception(f"Failed to get devices: {response_json}")
        else:
            logging.debug(f"Successfully got devices: {response_json}")
        return [Device(**device) for device in response.json()["data"]]

    def get_device_status(self, device: Device):
        payload = {
            "requestId": str(uuid.uuid4()),
            "payload": {"sku": device.sku, "device": device.id},
        }
        response = requests.post(
            f"{self.base_url}/router/api/v1/device/state",
            headers={"Content-Type": "application/json", "Govee-API-Key": self.api_key},
            json=payload,
        )
        response_json = response.json()
        if response.status_code != 200 and response_json["message"] != "success":
            logging.error(
                f"Failed to get device status for device {device.id}: {response_json}"
            )
        else:
            logging.debug(
                f"Successfully got device status for device {device.id}: {response_json}"
            )
        return response_json

    @property
    def lighting_devices(self):
        return [device for device in self.devices if device.sku in ["H61E6"]]

    @property
    def temperature_devices(self):
        return [device for device in self.devices if device.sku in ["H5110"]]

    def set_brightness(self, device: Device, brightness: int):
        """Set brightness for a specific device"""
        payload = {
            "requestId": str(uuid.uuid4()),
            "payload": {
                "sku": device.sku,
                "device": device.id,
                "capability": {
                    "type": "devices.capabilities.range",
                    "instance": "brightness",
                    "value": brightness,
                },
            },
        }
        response = requests.post(
            f"{self.base_url}/router/api/v1/device/control",
            headers={"Content-Type": "application/json", "Govee-API-Key": self.api_key},
            json=payload,
        )
        response_json = response.json()
        if response.status_code != 200 and response_json["message"] != "success":
            logging.error(
                f"Failed to set brightness for device {device.id}: {response_json}"
            )
        else:
            logging.debug(f"Successfully set brightness for device {device.id}")
        return response_json

    def set_color_rgb(self, device: Device, rgb: tuple[int, int, int]):
        """Set RGB color for a specific device"""
        payload = {
            "requestId": str(uuid.uuid4()),
            "payload": {
                "sku": device.sku,
                "device": device.id,
                "capability": {
                    "type": "devices.capabilities.color_setting",
                    "instance": "colorRgb",
                    "value": rgb[0] << 16 | rgb[1] << 8 | rgb[2],
                },
            },
        }
        response = requests.post(
            f"{self.base_url}/router/api/v1/device/control",
            headers={"Content-Type": "application/json", "Govee-API-Key": self.api_key},
            json=payload,
        )
        response_json = response.json()
        if response.status_code != 200 and response_json["message"] != "success":
            logging.error(
                f"Failed to set color for device {device.id}: {response_json}"
            )
        else:
            logging.debug(f"Successfully set color for device {device.id}")
        return response_json

    def set_color_rgb_and_brightness_all_lights(
        self, rgb_value: int = None, brightness: int = None
    ):
        """Set RGB color and brightness for all devices"""
        for device in self.lighting_devices:
            if rgb_value:
                self.set_color_rgb(device, rgb_value)
            if brightness:
                self.set_brightness(device, brightness)

    def set_diy_scene(self, device: Device, scene: str = "working"):
        """Set DIY scene for a specific device"""
        if scene not in self.get_diy_scene(device):
            raise ValueError(f"Scene {scene} not found")
        else:
            logging.debug(f"Setting DIY scene for device {device.id}: {scene}")
        scene_value = self.get_diy_scene(device)[scene]
        payload = {
            "requestId": str(uuid.uuid4()),
            "payload": {
                "sku": device.sku,
                "device": device.id,
                "capability": {
                    "type": "devices.capabilities.diyScene",
                    "instance": "diyScene",
                    "value": scene_value,
                },
            },
        }
        response = requests.post(
            f"{self.base_url}/router/api/v1/device/control",
            headers={"Content-Type": "application/json", "Govee-API-Key": self.api_key},
            json=payload,
        )
        response_json = response.json()
        if response.status_code != 200 and response_json["message"] != "success":
            logging.error(
                f"Failed to set DIY scene for device {device.id}: {response_json}"
            )
        else:
            logging.debug(
                f"Successfully set DIY scene for device {device.id}: {response_json}"
            )
        return response_json

    def get_diy_scene(self, device: Device):
        """Get DIY scenes for a specific device"""
        payload = {
            "requestId": str(uuid.uuid4()),
            "payload": {"sku": device.sku, "device": device.id},
        }
        response = requests.post(
            f"{self.base_url}/router/api/v1/device/diy-scenes",
            headers={"Content-Type": "application/json", "Govee-API-Key": self.api_key},
            json=payload,
        )
        response_json = response.json()
        if response.status_code != 200 and response_json["message"] != "success":
            logging.error(
                f"Failed to get DIY scenes for device {device.id}: {response_json}"
            )
        else:
            logging.debug(
                f"Successfully got DIY scenes for device {device.id}: {response_json}"
            )
        # Parse capabilities to {name: value} format
        parsed_scenes = {}
        if response_json.get("code") == 200 and "payload" in response_json:
            capabilities = response_json["payload"].get("capabilities", [])
            for capability in capabilities:
                if capability.get("type") == "devices.capabilities.dynamic_scene":
                    parameters = capability.get("parameters", {})
                    options = parameters.get("options", [])
                    for option in options:
                        name = option.get("name")
                        value = option.get("value")
                        if name and value:
                            parsed_scenes[name] = value

        return parsed_scenes

    def use_preset_color(
        self,
        device: Device,
        preset_color: Literal[
            "working", "red", "blue", "green", "yellow", "purple", "white"
        ],
    ):
        if preset_color == "working":
            self.set_diy_scene(device, "working")
        else:
            color_map = {
                "red": (255, 0, 0),
                "blue": (0, 0, 255),
                "green": (0, 255, 0),
                "orange": (255, 165, 0),
                "yellow": (255, 255, 0),
                "purple": (255, 0, 255),
                "white": (255, 255, 255),
            }
            rgb = color_map.get(preset_color, (255, 255, 255))
            self.set_color_rgb(device, rgb)

    def use_preset_color_and_brightness_all_lights(
        self,
        preset_color: Literal[
            "working", "red", "orange", "blue", "green", "yellow", "purple", "white"
        ],
        brightness: int = None,
    ):
        for device in self.lighting_devices:
            self.use_preset_color(device, preset_color)
            if brightness:
                self.set_brightness(device, brightness)

    def read_temperature(self, device: Device):
        payload = {
            "requestId": f"uuid-{device.id}",
            "payload": {"sku": device.sku, "device": device.id},
        }
        response = requests.post(
            f"{self.base_url}/router/api/v1/device/state",
            headers={"Content-Type": "application/json", "Govee-API-Key": self.api_key},
            json=payload,
        )
        response_json = response.json()

        if response.status_code != 200 or response_json.get("code") != 200:
            logging.error(
                f"Failed to get status for device {device.id}: {response_json}"
            )
            return None

        # Check if device is online
        capabilities = response_json.get("payload", {}).get("capabilities", [])
        is_online = False
        temperature = None

        for capability in capabilities:
            if (
                capability.get("type") == "devices.capabilities.online"
                and capability.get("instance") == "online"
            ):
                is_online = capability.get("state", {}).get("value", False)
            elif (
                capability.get("type") == "devices.capabilities.property"
                and capability.get("instance") == "sensorTemperature"
            ):
                temperature = capability.get("state", {}).get("value")

        if not is_online:
            return None

        temperature = float(temperature)

        return (temperature - 32) * 5 / 9 if temperature is not None else None

    def read_all_temperature_devices(self):
        temperatures = {}
        for device in self.temperature_devices:
            temperature = self.read_temperature(device)
            temperatures[device.name] = temperature
        return temperatures


alabos_url = "http://192.168.1.89:8895/"
govee_client = GoveeClient(api_key="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")

previous_color = "unknown"


def get_user_input_from_alabos():
    try:
        response = requests.get(f"{alabos_url}api/userinput/pending", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data["pending_requests"]
        else:
            print(f"Failed to get user input: {response.status_code}")
            return None
    except Exception as e:
        print(f"Failed to get user input: {e}")
        return None


def read_supply_gas_pressure():
    try:
        response = requests.get("http://192.168.1.7", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("pressure_psi")
        else:
            print(f"Failed to get supply gas pressure: {response.status_code}")
            return None
    except Exception as e:
        print(f"Failed to get supply gas pressure: {e}")
        return None

slack_bot_token = "xoxb-xxxxxx"
slack_channel_id = "XXXXXXXXX"


def send_slack_message(message: str):
    try:
        response = requests.post("https://slack.com/api/chat.postMessage", json={"channel": slack_channel_id, "text": message}, headers={"Authorization": f"Bearer {slack_bot_token}"})
        if response.status_code == 200:
            return True
        else:
            print(f"Failed to send slack message: {response.status_code}")
            return False
    except Exception as e:
        print(f"Failed to send slack message: {e}")
        return False


# Global variables to track pressure alarm state
pressure_alarm_sent = False
last_pressure_status = "normal"  # "normal", "low", "high"


def check_and_send_pressure_alarm():
    global pressure_alarm_sent, last_pressure_status
    
    pressure = read_supply_gas_pressure()
    if pressure is None:
        return
    
    current_status = "normal"
    message = ""
    
    if pressure < 50:
        current_status = "low"
        message = f"⚠️ GPSS SUPPLY GASPRESSURE ALERT: Supply gas pressure is critically low at {pressure} PSI (below 50 PSI threshold)"
    elif pressure > 85:
        current_status = "high"
        message = f"⚠️ GPSS SUPPLY GAS PRESSURE ALERT: Supply gas pressure is critically high at {pressure} PSI (above 85 PSI threshold)"
    
    # Send alarm if status changed from normal to abnormal
    if current_status != "normal" and last_pressure_status == "normal":
        send_slack_message(message)
        pressure_alarm_sent = True
    
    # Reset alarm state when pressure returns to normal
    elif current_status == "normal" and last_pressure_status != "normal":
        send_slack_message(f"✅ GPSS SUPPLY GAS PRESSURE NORMAL: Supply gas pressure has returned to normal at {pressure} PSI")
        pressure_alarm_sent = False
    
    last_pressure_status = current_status

    return current_status

    
def change_light_by_lab_status():
    global previous_color
    light_changed = False
    user_input = get_user_input_from_alabos()
    input_level = 0
    if user_input is None:
        if previous_color != "white-off":
            govee_client.use_preset_color_and_brightness_all_lights(
                preset_color="white", brightness=2
            )
            previous_color = "white-off"
            light_changed = True
        return light_changed

    for eid, user_inputs_ in user_input.items():
        is_maintanance = eid == "Maintenance"
        for user_input_ in user_inputs_:
            if "A unrecoverable error has occurred." in user_input_["prompt"]:
                input_level = max(input_level, 50)  # mean error
            elif is_maintanance:
                input_level = max(input_level, 40)  # maintanance
            else:
                input_level = max(input_level, 10)  # normal

    pressure_status = check_and_send_pressure_alarm()
    if pressure_status == "low":
        input_level = max(input_level, 30)
    elif pressure_status == "high":
        input_level = max(input_level, 20)

    if input_level >= 50:
        if previous_color != "red":
            govee_client.use_preset_color_and_brightness_all_lights(
                preset_color="red", brightness=100
            )
            previous_color = "red"
            light_changed = True
    elif input_level >= 40:
        if previous_color != "orange":
            govee_client.use_preset_color_and_brightness_all_lights(
                preset_color="orange", brightness=100
            )
            previous_color = "orange"
            light_changed = True
    elif input_level >= 30:
        if previous_color != "blue":
            govee_client.use_preset_color_and_brightness_all_lights(
                preset_color="blue", brightness=100
            )
            previous_color = "blue"
            light_changed = True
    elif input_level >= 20:
        if previous_color != "purple":
            govee_client.use_preset_color_and_brightness_all_lights(
                preset_color="purple", brightness=80
            )
            previous_color = "purple"
            light_changed = True
    elif input_level >= 10:
        if previous_color != "yellow":
            govee_client.use_preset_color_and_brightness_all_lights(
                preset_color="yellow", brightness=40
            )
            previous_color = "yellow"
            light_changed = True
    else:
        if previous_color != "working":
            govee_client.use_preset_color_and_brightness_all_lights(
                preset_color="working", brightness=40
            )
            previous_color = "working"
            light_changed = True
    return light_changed

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    while True:
        try:
            light_changed = change_light_by_lab_status()
        except Exception:
            logging.error(f"Failed to change light: {traceback.format_exc()}")
        else:
            if light_changed:
                logging.info("Successfully changed light")
            else:
                logging.info("No light change")
        time.sleep(5)

