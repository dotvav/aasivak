## Aasivak

This program bridges your Hi-Kumo heater/air conditioner system with Home Assistant.

It uses Home Assistant MQTT discovery mechanism: https://www.home-assistant.io/docs/mqtt/discovery/ 

Checkout the project, either edit ```config/default.yml``` or create a ```config/local.yml``` with the properties you need to override. ```api_username``` and ```api_username``` are your Hi-Kumo app credentials. Then run ```Aasivak.py```.

Please use, clone and improve. Some things are not supported. It was tested only with my own devices and installation. This is a very early release, based on reverse engineering of the network traffic. I have no relation to Hitachi (other than using their product) and they may not like it. Use at your own perils.

## Installation

### Setup MQTT discovery on HA
You will need an MQTT broker: [MQTT broker](https://www.home-assistant.io/docs/mqtt/broker/)

And to activate MQTT discovery: [MQTT discovery](https://www.home-assistant.io/docs/mqtt/discovery/)

### Clone the Aasivak repo
```
git clone https://www.github.com/dotvav/aasivak.git
cd Aasivak
python3 -m pip install -r requirements.txt
```

### Change the configuration
You can either update the ```config/default.yml``` file or create a new file named ```config/local.yml```. The keys that are present in the local config will override the ones in the default config. If a key is absent from local config, Aasivak will fallback to the value of the default config. I recommend keeping the default config as is and make all the changes in the local config file so that you don't lose them when the default file gets updated from git.

You will need to set the ```api_username``` and ```api_password``` keys. You may need to set the ```mqtt_host``` key if your MQTT broker is not running on the same machine as Aasivak. 

* api_username: your Hi-Kumo login
* api_password: your Hi-Kumo password
* api_url: the Hi-Kumo API url (you should probably not touch this)
* api_user_agent: the user agent string that Aasivak will use in the header of its HTTP requests to the Hi-Kumo API

* mqtt_discovery_prefix: the MQTT topic prefix that HA is monitoring for discovery (you should probably not touch this) 
* mqtt_state_prefix: the MQTT topic prefix that Aasivak will use to broadcast the devices state to HA
* mqtt_command_prefix: the MQTT topic prefix that Aasivak will listen to for HA commands
* mqtt_host: the host name or ip address of the MQTT broker
* mqtt_client_name: the name that Aasivak will us on MQTT
* mqtt_username: set if your MQTT broker requires authentication
* mqtt_password: set if your MQTT broker requires authentication

* logging_level: Aasivak's logging level

### Start Aasivak manually
```
python3 Aasivak.py
```

### Start Aasivak as a systemd service
TODO


## Dependencies

- requests
- paho-mqtt
- pyyaml


