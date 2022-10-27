This is a tiny enhanced version of channels-mqtt-proxy。 
It Add MQTTSsupport for original channels-mqtt-proxy 

Installation:
pip install chanmqttsproxy

In Django settings.py , specify the credentials or certs , simillar as following example.
<pre>
# Local mqtt settings
MQTT_TLS = True
MQTT_CA = 'iotwebcore/certs/ca.crt'
MQTT_CERT = 'iotwebcore/certs/client1.crt'
MQTT_KEY = 'iotwebcore/certs/client1.key'
MQTT_HOST = "52.80.119.72"
#MQTT_USER = "mqtt-test"
#MQTT_PASSWORD = "mqtt-test"
MQTT_VERSION = 311  # defaults to 50
</pre>
other general usage just the same  

view original [channels-mqtt-proxy](https://github.com/lbt/channels-mqtt-proxy) for more information.