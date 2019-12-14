import json
import random
import time
import logging

import paho.mqtt.client as mqtt
import requests
import yaml


################

# TODO: figure out how to set and unset the "GREEN" state
# TODO: figure out how to set and unset the "leave_home" state

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
        "self.outdoor_temperature"
    ]

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
        self.discovery_topic = house.config.mqtt_discovery_prefix + "/climate/" + self.id + "/config"
        self.mqtt_config = {}
        self.topic_to_attr = {}

    def update_definitions(self, raw_definitions):
        for definition in raw_definitions:
            definition_name = definition["qualifiedName"]
            if definition_name in Device.raw_definition_attributes:
                setattr(self, Device.raw_definition_attributes[definition_name], definition["values"])

    def update_states(self, raw_states):
        for state in raw_states:
            state_name = state["name"]
            if state_name in Device.raw_state_attributes:
                attr_name = Device.raw_state_attributes[state_name]
                if attr_name in self.int_attributes:
                    setattr(self, attr_name, int(float(state["value"])))
                else:
                    setattr(self, attr_name, state["value"])

    def update_mqtt_config(self):
        self.mqtt_config = {
            "name": self.name,
            "unique_id": self.id,
            "payload_on": "on",
            "payload_off": "off",

            "current_temperature_topic": self.house.config.mqtt_state_prefix + "/" + self.id + "/temp",
            "mode_state_topic": self.house.config.mqtt_state_prefix + "/" + self.id + "/mode",
            "temperature_state_topic": self.house.config.mqtt_state_prefix + "/" + self.id + "/target_temp",
            "fan_mode_state_topic": self.house.config.mqtt_state_prefix + "/" + self.id + "/fan_mode",
            "swing_mode_state_topic": self.house.config.mqtt_state_prefix + "/" + self.id + "/swing_mode",

            "mode_command_topic": self.house.config.mqtt_command_prefix + "/" + self.id + "/mode",
            "temperature_command_topic": self.house.config.mqtt_command_prefix + "/" + self.id + "/target_temp",
            "fan_mode_command_topic": self.house.config.mqtt_command_prefix + "/" + self.id + "/fan_mode",
            "swing_mode_command_topic": self.house.config.mqtt_command_prefix + "/" + self.id + "/swing_mode",

            "modes": self.modes,
            "fan_modes": self.fan_modes,
            "swing_modes": self.swing_modes,
            "device": {"identifiers": self.id, "manufacturer": "Hitachi", "model": self.product_name}
        }
        self.topic_to_attr = {
            self.mqtt_config["mode_command_topic"]: "mode",
            self.mqtt_config["temperature_command_topic"]: "target_temperature",
            self.mqtt_config["fan_mode_command_topic"]: "fan_mode",
            self.mqtt_config["swing_mode_command_topic"]: "swing_mode"
        }

    def register_mqtt(self, discovery):
        mqtt_client = self.house.mqtt_client

        mqtt_client.subscribe(self.mqtt_config["mode_command_topic"], 0)
        mqtt_client.subscribe(self.mqtt_config["temperature_command_topic"], 0)
        mqtt_client.subscribe(self.mqtt_config["fan_mode_command_topic"], 0)
        mqtt_client.subscribe(self.mqtt_config["swing_mode_command_topic"], 0)
        # TODO leave_home_state?

        if discovery:
            mqtt_client.publish(self.discovery_topic, json.dumps(self.mqtt_config))

    def unregister_mqtt(self, discovery):
        mqtt_client = self.house.mqtt_client

        mqtt_client.unsubscribe(self.mqtt_config["mode_command_topic"], 0)
        mqtt_client.unsubscribe(self.mqtt_config["temperature_command_topic"], 0)
        mqtt_client.unsubscribe(self.mqtt_config["fan_mode_command_topic"], 0)
        mqtt_client.unsubscribe(self.mqtt_config["swing_mode_command_topic"], 0)
        # TODO leave_home_state?

        if discovery:
            mqtt_client.publish(self.discovery_topic, None)

    def on_message(self, topic, payload):
        attr = self.topic_to_attr.get(topic, None)
        if attr is not None:
            if attr in self.int_attributes:
                setattr(self, attr, int(float(payload)))
            else:
                setattr(self, attr, payload)
            self.send_state()

    def send_state(self):
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

    def publish_state(self):
        mqtt_client = self.house.mqtt_client
        if mqtt_client is not None:
            mqtt_client.publish(self.mqtt_config["current_temperature_topic"], self.temperature)
            mqtt_client.publish(self.mqtt_config["mode_state_topic"], self.mode)
            mqtt_client.publish(self.mqtt_config["temperature_state_topic"], self.target_temperature)
            mqtt_client.publish(self.mqtt_config["fan_mode_state_topic"], self.fan_mode)
            mqtt_client.publish(self.mqtt_config["swing_mode_state_topic"], self.swing_mode)


class Config:
    api_username = None
    api_password = None
    api_url = "https://ha117-1.overkiz.com/enduser-mobile-web/enduserAPI"
    api_user_agent = 'Dalvik/2.1.0 (Linux; U; Android 9; EML-L29 Build/HUAWEIEML-L29) application/hitachi'
    mqtt_discovery_prefix = "homeassistant"
    mqtt_state_prefix = "hikumo/state"
    mqtt_command_prefix = "hikumo/command"
    mqtt_host = "127.0.0.1"
    mqtt_port = 1883
    mqtt_username = None
    mqtt_password = None
    mqtt_client_name = "aasivak"
    logging_level = "INFO"

    def __init__(self, raw):
        self.api_username = raw["api_username"]
        self.api_password = raw["api_password"]
        self.api_user_agent = raw.get("api_user_agent", self.api_user_agent)
        self.mqtt_discovery_prefix = raw.get("mqtt_discovery_prefix", self.mqtt_discovery_prefix)
        self.mqtt_state_prefix = raw.get("mqtt_state_prefix", self.mqtt_state_prefix)
        self.mqtt_command_prefix = raw.get("mqtt_command_prefix", self.mqtt_command_prefix)
        self.mqtt_host = raw.get("mqtt_host", self.mqtt_host)
        self.mqtt_port = raw.get("mqtt_port", self.mqtt_port)
        self.mqtt_username = raw.get("mqtt_username", self.mqtt_username)
        self.mqtt_password = raw.get("mqtt_password", self.mqtt_password)
        self.mqtt_client_name = raw.get("mqtt_client_name", self.mqtt_client_name)
        self.logging_level = raw.get("logging_level", self.logging_level)


################

class HikumoAdapter:
    def __init__(self, config):
        self.config = config
        self.session = requests.Session()

    def get_api(self, url, data, headers, retry=1):
        try:
            response = self.session.get(url=url, data=data, headers=headers)
        except Exception as e:
            logging.warning(e)
            response = None

        if (response is None or response.status_code != 200) and retry > 0:
            self.login()
            return self.get_api(url, data, headers, retry - 1)
        else:
            return response

    def post_api(self, url, data, headers, retry=1):
        try:
            response = self.session.post(url=url, json=data, headers=headers)
        except Exception as e:
            logging.warning(e)
            response = None

        if (response is None or response.status_code != 200) and retry > 0:
            self.login()
            return self.post_api(url, data, headers, retry - 1)
        else:
            return response

    def login(self):
        url = self.config.api_url + "/login"
        data = {'userId': self.config.api_username, 'userPassword': self.config.api_password}
        headers = {'user-agent': self.config.api_user_agent,
                   'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'}
        self.session.post(url, data=data, headers=headers)
        logging.info("Logged into Hi-Kumo")

    def fetch_api_setup_data(self):
        url = self.config.api_url + "/setup"
        data = {}
        headers = {'user-agent': self.config.api_user_agent}
        response = self.get_api(url, data, headers, 1)
        return json.loads(response.text)


################

class House:
    def __init__(self):
        self.config = self.read_config()
        logging.basicConfig(level=self.config.logging_level, format="%(asctime)-15s %(levelname)-8s %(message)s")
        self.mqtt_client = mqtt.Client(self.config.mqtt_client_name)
        if self.config.mqtt_username is not None:
            self.mqtt_client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)
        self.mqtt_client.connect(self.config.mqtt_host, self.config.mqtt_port)
        self.devices = {}
        self.devices = {}
        self.hikumo = HikumoAdapter(self.config)
        self.hikumo.login()

    @staticmethod
    def read_config():
        with open("config/default.yml", 'r') as yml_file:
            raw_default_config = yaml.safe_load(yml_file)

        try:
            with open("config/local.yml", 'r') as yml_file:
                raw_local_config = yaml.safe_load(yml_file)
                raw_default_config.update(raw_local_config)
        except IOError:
            logging.info("No local config file found")

        return Config(raw_default_config)

    def register_all(self):
        for device_id, device in self.devices.items():
            device.register_mqtt(True)
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.loop_start()

    def unregister_all(self):
        self.mqtt_client.on_message(None)
        self.mqtt_client.loop_stop()
        for device_id, device in self.devices.items():
            device.unregister_mqtt(True)

    def refresh_all(self):
        raw_data = self.hikumo.fetch_api_setup_data()
        for raw_device in raw_data["devices"]:
            if raw_device["type"] == 1:
                device_id = raw_device["oid"]
                name = raw_device["label"]
                url = raw_device["deviceURL"]
                if device_id in self.devices:
                    device = self.devices[device_id]
                else:
                    device = Device(self, device_id, name, url)
                    self.devices[device.id] = device
                device.update_states(raw_device["states"])
                device.publish_state()

    def setup(self):
        raw_data = self.hikumo.fetch_api_setup_data()
        for raw_device in raw_data["devices"]:
            if raw_device["type"] == 1:
                device_id = raw_device["oid"]
                name = raw_device["label"]
                url = raw_device["deviceURL"]
                if device_id in self.devices:
                    device = self.devices[device_id]
                else:
                    device = Device(self, device_id, name, url)
                    self.devices[device.id] = device
                device.update_definitions(raw_device["definition"]["states"])
                device.update_states(raw_device["states"])
                device.update_mqtt_config()
                logging.info("Device found: %s (%s|%s)", device.name, device.id, device.command_url)

    def loop_start(self):
        self.setup()
        self.register_all()
        while True:
            time.sleep(29 + 2 * random.random())
            self.refresh_all()

    def on_message(self, client, userdata, message):
        topic_tokens = message.topic.split('/')
        # TODO validation

        device_id = topic_tokens[len(topic_tokens) - 2]
        command = topic_tokens[len(topic_tokens) - 1]
        value = str(message.payload.decode("utf-8"))

        logging.info("MQTT message received device '" + device_id + "' command '" + command + "' value '" + value + "'")

        device = self.devices.get(device_id, None)
        if device is not None:
            device.on_message(message.topic, value)


################

House().loop_start()
