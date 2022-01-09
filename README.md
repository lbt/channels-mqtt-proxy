# channels-mqtt-proxy

A Channels 3 compatible MQTT worker

This worker is a standard Channels Consumer which contains a
fully async MQTT server allowing channels messages to be used to
publish, subscribe to and receive MQTT messages

The proxy understands mqtt.subscribe and mqtt.publish so you can
change the topics dynamically.

When an MQTT subscribe is performed it is done on behalf of a channels
group and all Channels Consumers in that group will receive mqtt
messages as mqtt.message

The overview is :

MQTT <> Channels-MQTT-Proxy (in runworker) <> Redis/Channels-layer <> ASGI applications (in Daphne/runserver) <> Websockets/HTTP <> Browser


## Installation

```bash
pip install chanmqttproxy
```
## Usage

In Channels the asgi application handles all types of connection
routing.  Websocket and http connections are listened for by a
suitable server (eg daphne run by manage.py runserver) which will
instantiate classes and run objects to handle them. The 'mqtt'
Consumer does not accept incoming connections, just channel
messages. So it must be started as a worker which handles the Channel
messages; the MQTT client connection is then created inside the
MqttConsumer worker when the first channel message is received.

## Setup

The code may look familiar if you've used the Channels
[Chat tutorial](https://channels.readthedocs.io/en/stable/tutorial/index.html) :)

In fact it will add the ability to monitor the chat on the chat/<room>
MQTT channel and messages sent to that channel will appear on all
clients.


In `site/asgi.py`:

```python
	from chanmqttproxy import MqttConsumer
	from channels.routing import ChannelNameRouter
	
	application = ProtocolTypeRouter({
		"channel": ChannelNameRouter({
			"mqtt": MqttConsumer.as_asgi()
		}),
		... # rest of http/websocket routes
	})
```
To define the MQTT broker, in `site/settings.py`:

```python
# Local mqtt settings
MQTT_HOST = "mqtt.example.com"
MQTT_USER = "mqtt-test"
MQTT_PASSWORD = "mqtt-test"
MQTT_VERSION = 311  # defaults to 50
```

At this point you have a working async Channels/MQTT bridge

To subscribe to a topic in your AsyncConsumer

```python
    async def connect(self):
        ... # existing group_add() calls

        # Join mqtt group
        await self.channel_layer.group_add(
            "mqttgroup",
            self.channel_name
        )
        # Ensure MQTT messages come to the room
        # This simplistic approach subscribes the room every
        # time a websocket connects but that's OK
        await self.channel_layer.send(
            "mqtt",
            {
                "type": "mqtt_subscribe",
                "topic": f"chat/{self.room_name}",
                "group": "mqttgroup",
        })

        await self.accept()  # existing accept() call
```
To handle messages from a topic in your AsyncConsumer

```python
    # Receive message from mqtt group and send to websocket
    async def mqtt_message(self, event):
        message = event['message']
        topic = messagep["topic"]
        payload = messagep["payload"]

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': payload
        }))
```
To publish messages to a topic in your AsyncConsumer

```python
   # Receive message from WebSocket
    async def receive(self, text_data):

        ... # existing group_send etc

        # Publish on mqtt too
        await self.channel_layer.send(
            "mqtt",
            {
                "type": "mqtt_publish",
                "publish": {  # These form the kwargs for mqtt.publish
                    "topic":  f"chat/{self.room_name}_out",
                    "payload": message,
                    "qos": 2,
                    "retain": False,
                    }
        })
```

For debug logging I use this at the end of settings.py:

```python
import logging.config

LOGGING_CONFIG = None

logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console': {
            # exact format is not important, this is the minimum information
            'format': '%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console',
        },
    },
    'loggers': {
    # root logger
        'chanmqttproxy': {
            'level': 'DEBUG',
            'handlers': ['console'],
        },
        'mysite': {
            'level': 'DEBUG',
            'handlers': ['console'],
        },
        'chat': {
            'level': 'DEBUG',
            'handlers': ['console'],
        },
    },
})
```

The complete code for the Channels Chat tutorial application (up to
part 3) with the channels-mqtt-proxy additions is here:
https://github.com/lbt/channels-mqtt-proxy/tree/main/examples

## Usage

Now run both of these (in different consoles)

```
./manage.py runserver
./manage.py runworker mqtt
```

Use your mqtt listener to listen to the topic `chat/lobby_out` and
publish to the topic `chat/lobby`

Notice that if you use chat/<room> for both topics then when the proxy
client publishes to the MQTT topic the message appears twice. This is
because even if you're the one that publishes a message, if you're
subscribed to the topic, you will receive it too.

If you make changes to the code note that the Channels runworker does
not auto-reload and will still hold old subscribe/group information.


# TODO/Issues

## Connect to MQTT at startup
The MqttConsumer is only instantiated after the first message arrives
rather than when the worker starts. This means it may not be connected
so the await self.mqttproxy.connected.wait() is required on every
subscribe/publish (which is not a lot of overhead but...

## Unsubscribing and no-more-clients
It's not clear how to issue an unsubscribe or deal with all clients
disconnecting. If this is done in the AsyncConsumer disconnect() then
it needs a client-count which is probably unreliable. Currently MQTT
messages will always be sent to the Channels group and it handles
member timeout as per
https://channels.readthedocs.io/en/stable/channel_layer_spec.html#capacity
and
https://channels.readthedocs.io/en/stable/channel_layer_spec.html#persistence

## retain'ed messages
On initial subscribtion all retained messages are dropped.  This is
not ideal when retained messages are used to indicate 'last known
state' for clients.

However this is an MQTT concept and doesn't carry over to Channels
unless we handle retention and continue to store messages for each
Channel client that subscribes - and then somehow only send retained
messages to that new client and not the existing clients who've seen
them once..

Ideally there would be a mechanism for the app to pre-subscribe and
send retained (and new) messages to code that could update the
'current state' model which would then be maintained and used to
initialise new browser clients.

## MqttConsumer in worker doesn't exit
There doesn't seem to be a way to tell the worker to exit on Ctrl-C if
we trap it to clean up the MQTT connections.  Also note that in some
situations the Ctrl-C fails. Eg if the broker doesn't support V5.0 and
fallback to V311 is underway.

# Thanks
Thanks to Gurtam for https://github.com/wialon/gmqtt which is a great asyncio
MQTT client that I use extensively in my HA systems and integrate with PyQt too.

The Channels tutorial was really helpful in understanding the concepts.

Also to Xavier Lesa for https://github.com/xavierlesa/channels-asgi-mqtt which
is based on the paho-mqtt synchronous library and inspired me to write this.
