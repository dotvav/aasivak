import json
import random
import threading
import time
import logging
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
import requests
import yaml


################

# TODO: refactor the code to make it clearer what's the Hi-Kumo adapter and what is the HA adapter
# TODO: figure out how to set and unset the "GREEN" state
# TODO: figure out how to set and unset the "leave_home" state
# TODO: from reading the protocol variables and the webapp javascript (https://pastebin.com/HZKsEPjU), it seems there is
#  a way to enable a "local mode" but I have not found how. I suspect (and secretly hope) that this would open a port on
#  the local network that allows direct commands without the need for bouncing through the Hi-Kumo/Overkiz cloud.

################

class Device:
    raw_state_attributes = {
        "hlrrwifi:MainOperationState": "power_state",
        "hlrrwifi:LeaveHomeState": "leave_home",
        "hlrrwifi:ModeChangeState": "mode",
        "hlrrwifi:SwingState": "swing_mode",
        "hlrrwifi:FanSpeedState": "fan_mode",
        "hlrrwifi:RoomTemperatureState": "temperature",
        "core:TargetTemperatureState": "target_temperature",
        "hlrrwifi:OutdoorTemperatureState": "outdoor_temperature",
        "core:ProductModelNameState": "product_name"
    }

    raw_definition_attributes = {
        "hlrrwifi:MainOperationState": "power_states",
        "hlrrwifi:ModeChangeState": "modes",
        "hlrrwifi:FanSpeedState": "fan_modes",
        "hlrrwifi:SwingState": "swing_modes",
    }

    int_attributes = [
        "temperature",
        "target_temperature",
        "outdoor_temperature"
    ]

    # Key = Hi-Kumo mode, Value = HA mode
    modes_map = {
        "auto": "auto",
        "cooling": "cool",
        #"autoCooling": "cool",
        "dehumidify": "dry",
        "fan": "fan_only",
        "heating": "heat",
        "off": "off"
    }

    # Key = HA mode, Value = Hi-Kumo mode
    rev_modes_map = {
        "auto": "auto",
        "cool": "cooling",
        "dry": "dehumidify",
        "fan_only": "fan",
        "heat": "heating",
        "off": "off"
    }

    def __init__(self, house, device_id, name, command_url):
        self.house = house
        self.id = device_id
        self.name = name
        self.command_url = command_url
        self.power_state = ""
        self.leave_home_state = ""
        self.mode = ""
        self.swing_mode = ""
        self.fan_mode = ""
        self.temperature = 0
        self.target_temperature = 0
        self.outdoor_temperature = 0
        self.product_name = ""
        self.available = ""
        self.climate_discovery_topic = house.config.mqtt_discovery_prefix + "/climate/" + self.id + "/config"
        self.outdoor_temp_sensor_discovery_topic = house.config.mqtt_discovery_prefix + "/sensor/" + self.id + "_outdoor_temp/config"
        self.climate_mqtt_config = {}
        self.outdoor_temp_sensor_mqtt_config = {}
        self.topic_to_attr = {}
        self.state_dirty = False  # state is considered dirty when changed locally and not yet sent to HiKumo

    def update_definitions(self, raw_definitions):
        for definition in raw_definitions:
            definition_name = definition["qualifiedName"]
            if definition_name in Device.raw_definition_attributes:
                setattr(self, Device.raw_definition_attributes[definition_name], definition["values"])
        self.modes.remove("autoCooling")
        self.modes.append("off")

    # Temperatures in HiKumo seem to be encoded as signed bytes and transported as integers in the json API
    def sanitize_temp(self, string):
        temp = int(float(string))
        if temp > 127:
            return temp - 256
        else:
            return temp

    def update_states(self, raw_states, availability):
        if self.state_dirty:
            # Do not update the current state of the device while it is dirty
            return

        if availability:
            self.available = "online"
        else:
            self.available = "offline"
        for state in raw_states:
            state_name = state["name"]
            if state_name in Device.raw_state_attributes:
                attr_name = Device.raw_state_attributes[state_name]
                if attr_name in self.int_attributes:
                    setattr(self, attr_name, self.sanitize_temp(state["value"]))
                elif attr_name == "mode" and state["value"] == "autoCooling":
                    setattr(self, attr_name, "cooling")
                else:
                    setattr(self, attr_name, state["value"])

    def update_mqtt_config(self):
        self.climate_mqtt_config = {
            "name": self.name,
            "unique_id": self.id,
            "payload_on": "on",
            "payload_off": "off",

            "current_temperature_topic": self.house.config.mqtt_state_prefix + "/" + self.id + "/temp",
            "mode_state_topic": self.house.config.mqtt_state_prefix + "/" + self.id + "/mode",
            "temperature_state_topic": self.house.config.mqtt_state_prefix + "/" + self.id + "/target_temp",
            "fan_mode_state_topic": self.house.config.mqtt_state_prefix + "/" + self.id + "/fan_mode",
            "swing_mode_state_topic": self.house.config.mqtt_state_prefix + "/" + self.id + "/swing_mode",
            "availability_topic": self.house.config.mqtt_state_prefix + "/" + self.id + "/availability",

            "mode_command_topic": self.house.config.mqtt_command_prefix + "/" + self.id + "/mode",
            "temperature_command_topic": self.house.config.mqtt_command_prefix + "/" + self.id + "/target_temp",
            "fan_mode_command_topic": self.house.config.mqtt_command_prefix + "/" + self.id + "/fan_mode",
            "swing_mode_command_topic": self.house.config.mqtt_command_prefix + "/" + self.id + "/swing_mode",

            "modes": list(filter(lambda m: m, map(lambda m: self.modes_map.get(m, None), self.modes))),
            "fan_modes": self.fan_modes,
            "swing_modes": self.swing_modes,
            "device": {"identifiers": self.id, "manufacturer": "Hitachi", "model": self.product_name}
        }
        self.topic_to_attr = {
            self.climate_mqtt_config["mode_command_topic"]: "mode",
            self.climate_mqtt_config["temperature_command_topic"]: "target_temperature",
            self.climate_mqtt_config["fan_mode_command_topic"]: "fan_mode",
            self.climate_mqtt_config["swing_mode_command_topic"]: "swing_mode"
        }
        self.outdoor_temp_sensor_mqtt_config = {
            "name": self.name + " (Outdoor temperature)",
            "device_class": "temperature",
            "unit_of_measurement": self.house.config.temperature_unit,
            "state_topic": self.house.config.mqtt_state_prefix + "/" + self.id + "/outdoor_temp"
        }

    def register_mqtt(self):
        mqtt_client = self.house.mqtt_client

        mqtt_client.subscribe(self.climate_mqtt_config["mode_command_topic"], 0)
        mqtt_client.subscribe(self.climate_mqtt_config["temperature_command_topic"], 0)
        mqtt_client.subscribe(self.climate_mqtt_config["fan_mode_command_topic"], 0)
        mqtt_client.subscribe(self.climate_mqtt_config["swing_mode_command_topic"], 0)
        # TODO leave_home_state?

        if self.house.config.mqtt_discovery:
            retain = self.house.config.mqtt_config_retain
            mqtt_client.publish(self.climate_discovery_topic,
                                json.dumps(self.climate_mqtt_config), qos=1, retain=retain)
            mqtt_client.publish(self.outdoor_temp_sensor_discovery_topic,
                                json.dumps(self.outdoor_temp_sensor_mqtt_config), qos=1, retain=retain)

    def unregister_mqtt(self):
        mqtt_client = self.house.mqtt_client

        mqtt_client.unsubscribe(self.climate_mqtt_config["mode_command_topic"], 0)
        mqtt_client.unsubscribe(self.climate_mqtt_config["temperature_command_topic"], 0)
        mqtt_client.unsubscribe(self.climate_mqtt_config["fan_mode_command_topic"], 0)
        mqtt_client.unsubscribe(self.climate_mqtt_config["swing_mode_command_topic"], 0)
        # TODO leave_home_state?

        if self.house.config.mqtt_discovery:
            retain = self.house.config.mqtt_config_retain
            mqtt_client.publish(self.climate_discovery_topic, None, retain=retain)
            mqtt_client.publish(self.outdoor_temp_sensor_discovery_topic, None, retain=retain)

    def on_message(self, topic, payload):
        self.state_dirty = True
        attr = self.topic_to_attr.get(topic, None)
        if attr is not None:
            if attr in self.int_attributes:
                setattr(self, attr, int(float(payload)))
            else:
                if attr == "mode":
                    if payload == "off":
                        self.power_state = "off"
                    else:
                        self.power_state = "on"
                        setattr(self, attr, self.read_mode(payload))
                else:
                    setattr(self, attr, payload)
            t = threading.Timer(self.house.config.action_delay, self.send_state)
            t.start()

    def send_state(self):
        if not self.state_dirty:
            return
        self.state_dirty = False
        data = {
            "actions": [{
                "commands": [{
                    "name": "globalControl",
                    "parameters": [
                        self.power_state,
                        self.target_temperature,
                        self.fan_mode,
                        self.mode,
                        self.swing_mode,
                        "off"  # TODO ? find out what this argument is. It is not leave_home_state
                    ]
                }],
                "deviceURL": self.command_url
            }],
            "label": "change air to air heat pump command"
        }
        self.house.hikumo.post_api(self.house.config.api_url + "/" + "exec/apply", data,
                                   {'content-type': 'application/json; charset=UTF-8',
                                    'user-agent': self.house.config.api_user_agent})

    # Translates the internal mode into HA mode
    def sanitize_mode(self):
        if self.power_state == "off":
            return "off"
        else:
            return self.modes_map[self.mode] or "auto"

    # Translates HA mode into internal mode
    def read_mode(self, mode):
        return self.rev_modes_map[mode] or "auto"

    def publish_state(self):
        mqtt_client = self.house.mqtt_client
        retain = self.house.config.mqtt_state_retain
        if mqtt_client is not None:
            mqtt_client.publish(self.climate_mqtt_config["current_temperature_topic"],
                                self.temperature, retain=retain)
            mqtt_client.publish(self.climate_mqtt_config["mode_state_topic"],
                                self.sanitize_mode(), retain=retain)
            mqtt_client.publish(self.climate_mqtt_config["temperature_state_topic"],
                                self.target_temperature, retain=retain)
            mqtt_client.publish(self.climate_mqtt_config["fan_mode_state_topic"],
                                self.fan_mode, retain=retain)
            mqtt_client.publish(self.climate_mqtt_config["swing_mode_state_topic"],
                                self.swing_mode, retain=retain)
            mqtt_client.publish(self.climate_mqtt_config["availability_topic"],
                                self.available, retain=retain)
            # Temperature sensors work better as float in HA, even though Hi-Kumo rounds it as an int
            mqtt_client.publish(self.outdoor_temp_sensor_mqtt_config["state_topic"],
                                float(self.outdoor_temperature), retain=retain)


################

class Config:
    api_username = None
    api_password = None
    api_url = "https://ha117-1.overkiz.com/enduser-mobile-web/enduserAPI"
    api_user_agent = 'aasivak'
    mqtt_discovery_prefix = "homeassistant"
    mqtt_state_prefix = "hikumo/state"
    mqtt_command_prefix = "hikumo/command"
    mqtt_reset_topic = "hikumo/reset"
    mqtt_host = "127.0.0.1"
    mqtt_port = 1883
    mqtt_discovery = True
    mqtt_config_retain = True
    mqtt_state_retain = True
    mqtt_username = None
    mqtt_password = None
    http_proxy = None
    https_proxy = None
    mqtt_client_name = "aasivak"
    logging_level = "INFO"
    action_delay = 0.5
    refresh_delays = [3, 5, 10, 30]
    refresh_delay_randomness = 2
    temperature_unit = "°C"

    def __init__(self, raw):
        self.api_username = raw["api_username"]
        self.api_password = raw["api_password"]
        self.api_url = raw["api_url"]
        self.api_user_agent = raw.get("api_user_agent", self.api_user_agent)
        self.mqtt_discovery_prefix = raw.get("mqtt_discovery_prefix", self.mqtt_discovery_prefix)
        self.mqtt_state_prefix = raw.get("mqtt_state_prefix", self.mqtt_state_prefix)
        self.mqtt_command_prefix = raw.get("mqtt_command_prefix", self.mqtt_command_prefix)
        self.mqtt_reset_topic = raw.get("mqtt_reset_topic", self.mqtt_reset_topic)
        self.mqtt_host = raw.get("mqtt_host", self.mqtt_host)
        self.mqtt_port = raw.get("mqtt_port", self.mqtt_port)
        self.mqtt_discovery = raw.get("mqtt_discovery", self.mqtt_discovery)
        self.mqtt_config_retain = raw.get("mqtt_config_retain", self.mqtt_config_retain)
        self.mqtt_state_retain = raw.get("mqtt_state_retain", self.mqtt_state_retain)
        self.mqtt_username = raw.get("mqtt_username", self.mqtt_username)
        self.mqtt_password = raw.get("mqtt_password", self.mqtt_password)
        self.http_proxy = raw.get("http_proxy", self.http_proxy)
        self.https_proxy = raw.get("https_proxy", self.https_proxy)
        self.mqtt_client_name = raw.get("mqtt_client_name", self.mqtt_client_name)
        self.logging_level = raw.get("logging_level", self.logging_level)
        self.action_delay = raw.get("action_delay", self.action_delay)
        self.refresh_delays = raw.get("refresh_delays", self.refresh_delays)
        self.refresh_delay_randomness = raw.get("refresh_delay_randomness", self.refresh_delay_randomness)
        self.temperature_unit = raw.get("temperature_unit",self.temperature_unit)


################

class HikumoAdapter:
    def __init__(self, config):
        self.config = config
        self.delayer = Delayer([1], 2)
        self.session = requests.Session()
        self.session.proxies = {}
        if config.http_proxy:
            self.session.proxies["http"] = config.http_proxy
        if config.https_proxy:
            self.session.proxies["https"] = config.https_proxy


    def get_api(self, url, data, headers, retry=1):
        try:
            response = self.session.get(url=url, data=data, headers=headers, timeout=(2, 5))
        except Exception as e:
            logging.warning(e)
            response = None

        if response is None:
            status_code = -1
        else:
            status_code = response.status_code

        if status_code != 200:
            if retry > 0:
                logging.debug("API call failed with status code %s. Retrying.", status_code)
                time.sleep(self.delayer.next())
                self.login()
                return self.get_api(url, data, headers, retry - 1)
            else:
                logging.warning("API call failed with status code %s. No more retry.", status_code)
                return response
        else:

            logging.debug("API response: %s", response.text)
            return response

    def post_api(self, url, data, headers, retry=1):
        try:
            response = self.session.post(url=url, json=data, headers=headers, timeout=(2, 5))
        except Exception as e:
            logging.warning(e)
            response = None

        if response is None:
            status_code = -1
        else:
            status_code = response.status_code

        if status_code != 200:
            if retry > 0:
                logging.debug("API call failed with status code %s. Retrying.", status_code)
                time.sleep(self.delayer.next())
                self.login()
                return self.post_api(url, data, headers, retry - 1)
            else:
                logging.warning("API call failed with status code %s. No more retry.", status_code)
                return response
        else:
            logging.debug("API response: %s", response.text)
            return response

    def login(self):
        url = self.config.api_url + "/login"
        data = {'userId': self.config.api_username, 'userPassword': self.config.api_password}
        headers = {'user-agent': self.config.api_user_agent,
                   'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'}

        try:
            self.session.post(url, data=data, headers=headers, timeout=(5, 10))
        except Exception as e:
            logging.warning(e)
            return

        logging.info("Logged into Hi-Kumo")

    def fetch_api_setup_data(self):
        url = self.config.api_url + "/setup"
        data = {}
        headers = {'user-agent': self.config.api_user_agent}
        response = self.get_api(url, data, headers, 1)
        if response is None:
            return {}
        else:
            return json.loads(response.text)


################

class Delayer:
    def __init__(self, delays, randomness):
        self.delays = delays
        self.delay_index = 0
        self.randomness = randomness

    def reset(self):
        self.delay_index = 0

    def next(self):
        delay = self.delays[self.delay_index] + self.randomness * (random.random() - .5)
        self.delay_index = min(len(self.delays) - 1, self.delay_index + 1)
        return delay


################

class House:
    def __init__(self):
        self.config = self.read_config()
        logging.basicConfig(level=self.config.logging_level, format="%(asctime)-15s %(levelname)-8s %(message)s")
        self.mqtt_client = mqtt.Client(self.config.mqtt_client_name)
        if self.config.mqtt_username is not None:
            self.mqtt_client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)
        self.mqtt_client.connect(self.config.mqtt_host, self.config.mqtt_port)
        self.gateways = {}
        self.devices = {}
        self.delayer = Delayer(self.config.refresh_delays, self.config.refresh_delay_randomness)
        self.hikumo = HikumoAdapter(self.config)
        self.hikumo.login()

    @staticmethod
    def read_config():
        with open("config/default.yml", 'r', encoding="utf-8") as yml_file:
            raw_default_config = yaml.safe_load(yml_file)

        try:
            with open("config/local.yml", 'r', encoding="utf-8") as yml_file:
                raw_local_config = yaml.safe_load(yml_file)
                raw_default_config.update(raw_local_config)
        except IOError:
            logging.info("No local config file found")

        return Config(raw_default_config)

    def register_all(self):
        self.mqtt_client.loop_start()
        for device_id, device in self.devices.items():
            device.register_mqtt()
        self.mqtt_client.subscribe(self.config.mqtt_reset_topic, 0)
        self.mqtt_client.on_message = self.on_message

    def unregister_all(self):
        self.mqtt_client.on_message(None)
        self.mqtt_client.unsubscribe(self.config.mqtt_reset_topic, 0)
        for device_id, device in self.devices.items():
            device.unregister_mqtt()
        self.mqtt_client.loop_stop()

    def is_available(self, url):
        gateway_id = urlparse(url).netloc
        raw_gateway = self.gateways[gateway_id]
        if raw_gateway is not None:
            return bool(raw_gateway["alive"])
        else:
            return False

    def update_all_devices(self):
        raw_data = self.hikumo.fetch_api_setup_data()
        if "gateways" in raw_data and "devices" in raw_data:
            for raw_gateway in raw_data["gateways"]:
                gateway_id = raw_gateway["gatewayId"]
                self.gateways[gateway_id] = raw_gateway
            for raw_device in raw_data["devices"]:
                if raw_device["type"] == 1:
                    device_id = raw_device["oid"]
                    name = raw_device["label"]
                    url = raw_device["deviceURL"]
                    available = self.is_available(url)
                    if device_id in self.devices:
                        device = self.devices[device_id]
                    else:
                        device = Device(self, device_id, name, url)
                        self.devices[device.id] = device
                    device.update_definitions(raw_device["definition"]["states"])
                    device.update_states(raw_device["states"], available)

    def refresh_all(self):
        self.update_all_devices()
        for device in self.devices.values():
            device.publish_state()

    def setup(self):
        self.update_all_devices()
        for device in self.devices.values():
            device.update_mqtt_config()
            # device.publish_state()
            logging.info("Device found: %s (%s|%s)", device.name, device.id, device.command_url)

    def loop_start(self):
        self.setup()
        self.register_all()
        while True:
            self.refresh_all()
            time.sleep(self.delayer.next())

    def on_message(self, client, userdata, message):
        if message.topic == self.config.mqtt_reset_topic:
            self.setup()
            self.register_all()
            return

        topic_tokens = message.topic.split('/')
        # TODO validation

        device_id = topic_tokens[len(topic_tokens) - 2]
        command = topic_tokens[len(topic_tokens) - 1]
        value = str(message.payload.decode("utf-8"))
        logging.info("MQTT message received device '" + device_id + "' command '" + command + "' value '" + value + "'")

        device = self.devices.get(device_id, None)
        if device is not None:
            device.on_message(message.topic, value)
        self.delayer.reset()


################

House().loop_start()
