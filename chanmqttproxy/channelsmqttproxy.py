import asyncio
import functools
import json
import logging
import os
import signal
import socket
import ssl

from gmqtt import Client as MQTTClient
from gmqtt.mqtt.handler import MQTTConnectError
from gmqtt.mqtt.constants import MQTTv311, MQTTv50

LOGGER = logging.getLogger(__name__)


class ChannelsMQTTProxy:
    def __init__(self, channel_layer, settings):
        self.channel_layer = channel_layer

        # MQTTClient takes an identifier which is seen at the broker
        # Creating the client does not connect.
        self.mqtt = MQTTClient(
            f"ChannelsMQTTProxy@{socket.gethostname()}.{os.getpid()}")
        try:
            self.mqtt.set_auth_credentials(username=settings.MQTT_USER,
                                        password=settings.MQTT_PASSWORD)
        except AttributeError:
            # Settings are not defined. Try anonymous connection
            pass
        self.mqtt_host = settings.MQTT_HOST
        try:
            self.mqtt_port = settings.MQTT_PORT
        except AttributeError:
            # Setting not defined. Use default unsecured.
            self.mqtt_port = 1883
        # Set ssl
        try:
            self.mqtt_usessl = settings.MQTT_USE_SSL
        except AttributeError:
            # Setting is not defined. Assume false
            self.mqtt_usessl = False

        try:
            self.mqtt_ssl_ca = settings.MQTT_SSL_CA
            self.mqtt_ssl_cert = settings.MQTT_SSL_CERT
            self.mqtt_ssl_key = settings.MQTT_SSL_KEY
            try:
                self.mqtt_ssl_verify = settings.MQTT_SSL_VERIFY
            except AttributeError:
                # Assume True on error
                self.mqtt_ssl_verify = True
        except AttributeError:
            # Setting is not defined. Set safe values.
            self.mqtt_ssl_ca = None
            self.mqtt_ssl_cert = None
            self.mqtt_ssl_key = None
            self.mqtt_ssl_verify = True

        try:
            self.mqtt_version = settings.MQTT_VERSION
        except AttributeError:
            self.mqtt_version = 50
        # Hook up the callbacks and some lifecycle management events
        self.mqtt.on_connect = self._on_connect
        self.mqtt.on_disconnect = self._on_disconnect
        self.mqtt.on_message = self._on_subscribe
        self.mqtt.on_message = self._on_message
        self.stop_event = asyncio.Event()
        self.connected = asyncio.Event()

        try:
            self.mqtt_channel_name = settings.MQTT_CHANNEL_NAME
        except AttributeError:
            self.mqtt_channel_name = "mqtt"
        self.mqtt_channel_publish = f"{self.mqtt_channel_name}.publish"
        self.mqtt_channel_message = f"{self.mqtt_channel_name}.message"
        self.subscriptions = {}

    async def run(self):
        """This connects to the mqtt broker (retrying forever) and then waits
        for :func:`finish()` Once connected the underlying qmqtt
        client will re-connect if the connection is lost.
        """
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self.ask_exit)
        loop.add_signal_handler(signal.SIGTERM, self.ask_exit)
        await self.connect()
        await self.finish()

    async def connect(self):
        # Connect to the broker
        if self.mqtt_version == 311:
            version = MQTTv311
        else:
            version = MQTTv50

        while not self.mqtt.is_connected:
            try:
                LOGGER.debug('Connecting to mqtt%s://%s:%s using v%s',
                             "s" if self.mqtt_usessl else "",
                             self.mqtt_host,
                             self.mqtt_port,
                             self.mqtt_version)
                use_ssl = self.mqtt_usessl
                if (self.mqtt_usessl) and (self.mqtt_ssl_ca is not None):
                    LOGGER.debug('Using CA: %s Cert: %s Key: %s Verify: %s',
                                 self.mqtt_ssl_ca,
                                 self.mqtt_ssl_cert,
                                 self.mqtt_ssl_key,
                                 self.mqtt_ssl_verify)
                    try:
                        use_ssl = ssl.create_default_context(
                            ssl.Purpose.SERVER_AUTH,
                            cafile = self.mqtt_ssl_ca)
                        use_ssl.check_hostname = self.mqtt_ssl_verify
                        if self.mqtt_ssl_verify:
                            use_ssl.verify_mode = ssl.CERT_REQUIRED
                        else:
                            use_ssl.verify_mode =ssl.CERT_NONE
                        use_ssl.load_cert_chain(
                            certfile=self.mqtt_ssl_cert,
                            keyfile=self.mqtt_ssl_key)
                    except ssl.SSLError as e:
                        LOGGER.error('Error initialising ssl: %s. Retrying.',e)
                        await asyncio.sleep(1)
                        continue
                await self.mqtt.connect(
                    self.mqtt_host,
                    port=self.mqtt_port,
                    ssl=use_ssl,
                    version=version)
            except MQTTConnectError as e:
                # Mqtt server returned an error.
                # Back off as to not spam the server
                LOGGER.info('MQTT Error trying to connect: %s. Retrying.',e)
                # Close the connection since it is running and gmqtt will
                # still retry to complete the connection.
                await self.mqtt.disconnect()
                await asyncio.sleep(30)
            except Exception as e:
                LOGGER.warn(f"Error trying to connect: {e}. Retrying.")
                await asyncio.sleep(1)
        self.connected.set()

    async def finish(self):
        # This will wait until the client is signalled
        LOGGER.debug("Waiting for stop event")
        await self.stop_event.wait()
        await self.mqtt.disconnect()
        LOGGER.debug("MQTT client disconnected")

    def _on_connect(self, _client, _flags, _rc, _properties):
        LOGGER.debug('Connected')
        for s in self.subscriptions.keys():
            LOGGER.debug(f"Re-subscribing to {s}")
            self.mqtt.subscribe(s)

    def _on_disconnect(self, _client, _packet, _exc=None):
        LOGGER.debug('Disconnected')

    async def _on_message(self, _client, topic, payload, qos, properties):
        LOGGER.debug(f"{topic} => '{payload}' props:{properties}")

        # Check properties for 'retain' (which in this context means
        # the message is being sent from retained backing store) and
        # drop those.
        # Eventually find a way to direct these to support code which can build
        # initial state and keep it up-to-date? This is linked to
        # connect-on-startup.
        if properties["retain"] == 1:
            LOGGER.debug(f"Dropping replayed retained message")
            return

        # Compose a Channel message
        payload = payload.decode("utf-8")
        try:
            payload = json.loads(payload)
        except:
            LOGGER.debug("Payload is not JSON - sending it raw")
            pass
        msg = {
            "topic": topic,
            "payload": payload,
            "qos": qos,
        }
        event = {
            "type": self.mqtt_channel_message,  # default "mqtt.message"
            "message": msg
        }

        tasks = list()
        for grp in self.groups_matching_topic(topic):
            tasks.append(self.channel_layer.group_send(grp, event))
            LOGGER.debug(f"Calling {grp} handler for {topic}")
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            LOGGER.error("Cannot send event: {event}")
            LOGGER.exception(e)

    def subscribe(self, topic, group):
        """Subscribes a group to an MQTT topic (passed directly to MQTT)"""
        if topic not in self.subscriptions:
            LOGGER.debug(f"New subscription for {topic}")
            self.subscriptions[topic] = []
            # We need to mqtt-subscribe now:

            # This actually just sends a subscribe packet. We should
            # store this and the details and handle the setup in
            # _on_subscribe callback when the _mid (message id) is
            # confirmed.
            _mid = self.mqtt.subscribe(topic)
        else:
            if group in self.subscriptions[topic]:
                LOGGER.debug(f"{group} already subscibed to {topic}")
                return

        LOGGER.debug(f"{group} subscribed to {topic}")
        self.subscriptions[topic].append(group)

    def _on_subscribe(self, _client, _mid, _qos, _properties):
        LOGGER.debug('Subscribe callback {_mid}')

    async def unsubscribe(self, topic, group):
        """Un subscribes a group to an MQTT topic"""
        LOGGER.debug(f"unsubscribe {group} from {topic}")
        if topic in self.subscriptions:
            groups = self.subscriptions[topic]
            if group in groups:
                LOGGER.debug(f"{group} being unsubscribed from {topic}")
                groups.delete(topic)
            else:
                LOGGER.debug(f"{group} not subscribed to {topic}")
            if not len(groups):
                LOGGER.debug(f"No more {group}s, unsubscribing to {topic}")
                self.mqtt.unsubscribe(topic)
        LOGGER.debug(f"{topic} not subscribed")

    def publish(self, topic=None, payload=None, qos=2, retain=True):
        """Publish :param payload: to :param topic:"""
        LOGGER.debug(f"Publishing {topic} = {payload}")
        self.mqtt.publish(topic, payload, qos=qos, retain=retain)

    def ask_exit(self):
        """Handle outstanding messages and cleanly disconnect"""
        LOGGER.warning(f"{self} received signal asking to exit")
        self.stop_event.set()

    def groups_matching_topic(self, topic):
        groups = set()
        for sub, gs in self.subscriptions.items():
            if sub == topic:  # simple match
                groups.update(gs)
            elif self.topic_matches_sub(sub, topic):
                LOGGER.debug(f"Found matching groups {gs}")
                groups.update(gs)
        return groups

    # Taken from paho-mqtt - thanks :)
    @staticmethod
    def topic_matches_sub(sub, topic):
        """Check whether a topic matches a subscription.
        For example:
        foo/bar would match the subscription foo/# or +/bar
        non/matching would not match the subscription non/+/+
        """
        result = True
        multilevel_wildcard = False

        slen = len(sub)
        tlen = len(topic)

        if slen > 0 and tlen > 0:
            if (sub[0] == '$' and topic[0] != '$') or (topic[0] == '$' and sub[0] != '$'):
                return False

        spos = 0
        tpos = 0

        while spos < slen and tpos < tlen:
            if sub[spos] == topic[tpos]:
                if tpos == tlen-1:
                    # Check for e.g. foo matching foo/#
                    if spos == slen-3 and sub[spos+1] == '/' and sub[spos+2] == '#':
                        result = True
                        multilevel_wildcard = True
                        break

                spos += 1
                tpos += 1

                if tpos == tlen and spos == slen-1 and sub[spos] == '+':
                    spos += 1
                    result = True
                    break
            else:
                if sub[spos] == '+':
                    spos += 1
                    while tpos < tlen and topic[tpos] != '/':
                        tpos += 1
                    if tpos == tlen and spos == slen:
                        result = True
                        break

                elif sub[spos] == '#':
                    multilevel_wildcard = True
                    if spos+1 != slen:
                        result = False
                        break
                    else:
                        result = True
                        break

                else:
                    result = False
                    break

        if not multilevel_wildcard and (tpos < tlen or spos < slen):
            result = False

        return result
