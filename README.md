# NOT MAINTAINED ANYMORE

Hi, 

This bridge has served me well for a few years. Some of you have used it, forked it. As an HomeAssistant user, I am now more fulfilled with the official [Overkiz integration](https://www.home-assistant.io/integrations/overkiz/). I have joined forces with the talented contributors of this project to get the same functionnality directly in the stock HomeAssistant, starting from version [2023.12](https://www.home-assistant.io/changelogs/core-2023.12).

Feel free to keep using, forking and improving this project if you find it useful.

Cheers!

---

## Aasivak

This program bridges your Hi-Kumo heater/air conditioner system with Home Assistant.

It uses Home Assistant MQTT discovery mechanism: https://www.home-assistant.io/docs/mqtt/discovery/ 

Checkout the project, either edit ```config/default.yml``` or create a ```config/local.yml``` with the properties you need to override. ```api_username``` and ```api_password``` are your Hi-Kumo app credentials. Then run ```Aasivak.py```.

Please use, clone and improve. Some things are not supported. It was tested only with my own devices and installation. This is a very early release, based on reverse engineering of the network traffic. I have no relation to Hitachi (other than using their product) and they may not like it. Use at your own perils.

## Installation

### Setup MQTT discovery on HA
You will need an MQTT broker: [MQTT broker](https://www.home-assistant.io/docs/mqtt/broker/)

And to activate MQTT discovery: [MQTT discovery](https://www.home-assistant.io/docs/mqtt/discovery/)

### Clone the Aasivak repo
```shell script
git clone https://www.github.com/dotvav/aasivak.git
cd aasivak
pip3 install -r requirements.txt
```

### Change the configuration
You can either update the ```config/default.yml``` file or create a new file named ```config/local.yml```. The keys that are present in the local config will override the ones in the default config. If a key is absent from local config, Aasivak will fallback to the value of the default config. I recommend keeping the default config as is and make all the changes in the local config file so that you don't lose them when the default file gets updated from git.

You will need to set the ```api_username``` and ```api_password``` keys. You may need to set the ```mqtt_host``` key if your MQTT broker is not running on the same machine as Aasivak. 

Property | Usage | Note
--- | --- | ---
**`api_username`** | your Hi-Kumo login | You **must** set this.
**`api_password`** | your Hi-Kumo password | You **must** set this.
`api_url` | the Hi-Kumo API url | you should probably not touch this.
`api_user_agent` | the user agent string that Aasivak will use in the header of its HTTP requests to the Hi-Kumo API.
`mqtt_discovery_prefix` | the MQTT topic prefix that HA is monitoring for discovery | You should probably not touch this. HA's default is `homeassistant`. 
`mqtt_state_prefix` | the MQTT topic prefix that Aasivak will use to broadcast the devices state to HA | You should probably not touch this.
`mqtt_command_prefix` | the MQTT topic prefix that Aasivak will listen to for HA commands | You should probably not touch this.
`mqtt_reset_topic` | the MQTT topic where Aasivak receives reset commands | Send any message on this topic to tell Aasivak it must re-register all the devices. You should create an automation to do that every time HA starts.
**`mqtt_host`** | the host name or ip address of the MQTT broker | Use `localhost` or `127.0.0.1` if the MQTT broker runs on the same machine as Aasivak.
`mqtt_client_name` | the name that Aasivak will us on MQTT | You should probably not touch this.
`mqtt_discovery` | `on` to enable MQTT auto-discovery in HA | Change to `off` if you don't use HA or if you prefer configuring your devices manually 
`mqtt_config_retain` | `on` to retain configuration messages in MQTT | Change to `off` if you cannotor prefer not to retain config messages
`mqtt_state_retain` | `on` to retain state messages in MQTT | Change to `off` if you cannot or prefer not to retain state messages
`mqtt_username` | the MQTT broker username | This is needed only if the MQTT broker requires an authenticated connection.
`mqtt_password` | the MQTT broker password | This is needed only if the MQTT broker requires an authenticated connection.
`http_proxy` | an http proxy URL | This is only needed if you need to route your http traffic through a proxy
`https_proxy` | an https proxy URL | This is only needed if you need to route your https traffic through a proxy
`temperature_unit` | the temperature measurement unit | `°C` by default.
`action_delay` | how many seconds to wait before executing an action | `0.5` by default. The more you wait, the more likely consecutive actions will be sent in one single command to Hi-Kumo. This can be useful with automations that trigger several actions if you don't want the AC unit to beep as many times.
`refresh_delays` | list of waiting durations before calling the Hi-Kumo API to refresh devices state | If you set `[2, 5, 10, 30]` then Aasivak will call the Hi-Kumo API to refresh its state after 2s, then 5s, then 10s, and then every 30s. The delay is reset to 2s when Aasivak receives a command from HA. Some randomness is added to these delays: every time Aasivak needs to wait, it adds or remove up to `logging_delay_randomness/2` to the delay. 
`refresh_delay_randomness` | maximum number of seconds to add to all the waiting durations | See `refresh_delays`. Use `0` for no randomness.
`logging_level` | Aasivak's logging level | INFO


### Start Aasivak manually
```shell script
python3 Aasivak.py
```

### Start Aasivak as a systemd service
Create the following ```/etc/systemd/system/aasivak.service``` file (change the paths as required):

```
[Unit]
Description=Aasivak
Documentation=https://github.com/dotvav/aasivak
After=network.target

[Service]
Type=simple
User=homeassistant
WorkingDirectory=/home/homeassistant/aasivak
ExecStart=/usr/bin/python3 /home/homeassistant/aasivak/Aasivak.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
You may want to start this after the MQTT broker or HA has started: add the appropriate ```After=``` statement.

Run the following to enable and run the service, and see what its status is:
```shell script
sudo systemctl enable aasivak.service
sudo systemctl start aasivak.service
sudo systemctl status aasivak.service
```

## Pull the latest version from Github
Get the latest source
```shell script
cd aasivak
git pull origin master
```
Then restart the systemd service (if you created one):
```shell script
sudo systemctl status aasivak.service
```

## Dependencies
- requests
- paho-mqtt
- pyyaml


## Example of HomeAssistant automation
Hi-Kumo's weekly scheduler is annoyingly ignoring the swing mode and fan speed setup of my units, and always resets them
to their default value when it sends an update (blowing directly downwards with "auto" speed). The AC unit is just over
my bed and I hate getting blown hot air in my face while I sleep. I have set the below automation in homeassistant: 
whenever the fan_mode is set to 'off' (which means Hi-Kumo has sent a command to my unit) I reset it to 'both', and set
the fan speed to 'silent'. The only downside is the 3 beeps that the AC unit makes (one because of the first Hi-Kumo 
command, one for resetting the swing mode, and one for resetting the fan speed). 

```yaml
- id: '1234567890123'
  alias: Reset AC swing mode and fan speed in the bedroom
  description: Reset AC swing mode and fan speed in the bedroom
  trigger:
  - platform: template
    value_template: '{{ is_state_attr(''climate.bedroom'', ''swing_mode'', ''stop'') }}'
  condition: []
  action:
  - service: climate.set_swing_mode
    data:
      entity_id: climate.bedroom
      swing_mode: both
  - service: climate.set_fan_mode
    data:
      entity_id: climate.bedroom
      fan_mode: silent
```
