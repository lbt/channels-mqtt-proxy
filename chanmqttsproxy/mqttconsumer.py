import asyncio
import logging
import sys
from channels.consumer import AsyncConsumer
from channels.exceptions import StopConsumer
from channels.layers import get_channel_layer
from django.conf import settings

from .channelsmqttproxy import ChannelsMQTTProxy

LOGGER = logging.getLogger(__name__)


class MqttConsumer(AsyncConsumer):
    """The MqttConsumer is run as a channels worker. It starts an MQTT
    client and handles subscription and message distribution via
    Channels messages.
    """

    def __init__(self):
        super().__init__()
        self.mqttproxy = ChannelsMQTTProxy(get_channel_layer(),
                                           settings)
        self.task = asyncio.create_task(self.mqttproxy.run())
        self.task.add_done_callback(self.finish)

    def finish(self, task):
        # For some reason the Channels worker doesn't seem to exit
        # if there's a task with a loop signal handler
        sys.exit(0)

    async def mqtt_subscribe(self, event):
        """This is the mqtt.subscribe channel message handler.  It subscribes
        a channel group to a topic.  All messages received for that
        topic will be sent to all members of the group using
        'mqtt.message'. Multiple subscriptions are allowed.  The topic
        uses MQTT wildcard syntax. The same topic may be subscibed by
        multiple channel groups

        """
        topic = event['topic']
        group = event['group']
        LOGGER.debug(f"subscribe to {topic} for {group}")
        await self.mqttproxy.connected.wait()
        self.mqttproxy.subscribe(topic, group)

    async def mqtt_publish(self, event):
        """The event contains a publish dict which is used by the mqtt client.
        The values : topic, payload, qos & retain may be specified.
        """
        LOGGER.debug(event)
        publish = event['publish']
        # do something with topic and payload
        LOGGER.debug(f"MQTT publish ({publish})")
        await self.mqttproxy.connected.wait()
        self.mqttproxy.publish(**publish)
