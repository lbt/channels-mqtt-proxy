This is a tiny enhanced version of channels-mqtt-proxy。 
It Add MQTTSsupport for original channels-mqtt-proxy . mqtts is mandatory for some IoT platform like AWS.

Installation:
<pre>
pip install chanmqttsproxy
</pre>

In Django settings.py , specify the credentials or certs , simillar as following example.
<pre>
# Local mqtt settings
MQTT_TLS = True
MQTT_CA = 'app/certs/ca.crt'
MQTT_CERT = 'app/certs/client1.crt'
MQTT_KEY = 'app/certs/client1.key'
MQTT_HOST = 'x.x.x.x'
#MQTT_USER = 'mqtt-test'
#MQTT_PASSWORD = 'mqtt-test'
MQTT_VERSION = 311  # defaults to 50
</pre>
other general usage just the same  

view original [channels-mqtt-proxy](https://github.com/lbt/channels-mqtt-proxy) for more information.
