"""
Tests for comms/transport/nodered_mqtt.py.
paho-mqtt Client is fully mocked — no broker required.
"""
import asyncio
import pytest
from unittest.mock import MagicMock, patch

from comms.transport.nodered_mqtt import NodeRedMQTTTransport
from comms.dcn_packet import build_packet


def _make(name="test", **overrides):
    cfg = {
        "broker": "localhost",
        "port": 1883,
        "topic_rx": "dcn/control/rx",
        "topic_tx": "dcn/control/tx",
    }
    cfg.update(overrides)
    return NodeRedMQTTTransport(name, cfg)


def _mqtt_patch():
    patcher = patch("comms.transport.nodered_mqtt.mqtt.Client")
    mock_cls = patcher.start()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance
    return patcher, mock_cls, mock_instance


# ---------------------------------------------------------------------------
# Default topic derivation
# ---------------------------------------------------------------------------

class TestTopicDefaults:

    def test_topics_derived_from_name_when_not_configured(self):
        t = NodeRedMQTTTransport("mynet", {})
        assert t._topic_rx == "dcn/mynet/rx"
        assert t._topic_tx == "dcn/mynet/tx"

    def test_explicit_topics_respected(self):
        t = _make(topic_rx="custom/rx", topic_tx="custom/tx")
        assert t._topic_rx == "custom/rx"
        assert t._topic_tx == "custom/tx"


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------

class TestConnect:

    async def test_connect_async_called_with_broker_and_port(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make(broker="192.168.1.10", port=1884)
            await t.connect()
            mock_inst.connect_async.assert_called_once_with(
                "192.168.1.10", 1884, keepalive=60
            )
        finally:
            patcher.stop()

    async def test_loop_start_called(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            await t.connect()
            mock_inst.loop_start.assert_called_once()
        finally:
            patcher.stop()

    async def test_username_set_when_provided(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make(username="user", password="secret")
            await t.connect()
            mock_inst.username_pw_set.assert_called_once_with("user", "secret")
        finally:
            patcher.stop()

    async def test_no_username_pw_when_empty_string(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make(username="", password="")
            await t.connect()
            mock_inst.username_pw_set.assert_not_called()
        finally:
            patcher.stop()

    async def test_callbacks_registered(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            await t.connect()
            assert mock_inst.on_connect is not None
            assert mock_inst.on_disconnect is not None
            assert mock_inst.on_message is not None
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------

class TestDisconnect:

    async def test_loop_stop_called(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            await t.connect()
            await t.disconnect()
            mock_inst.loop_stop.assert_called_once()
        finally:
            patcher.stop()

    async def test_disconnect_called_on_client(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            await t.connect()
            await t.disconnect()
            mock_inst.disconnect.assert_called_once()
        finally:
            patcher.stop()

    async def test_connected_cleared(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            await t.connect()
            t._connected = True
            await t.disconnect()
            assert not t.connected
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------

class TestSend:

    async def test_send_publishes_to_topic_tx(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            await t.connect()
            t._connected = True

            pkt = build_packet("01", "STATE")
            await t.send(pkt)

            mock_inst.publish.assert_called_once_with(
                "dcn/control/tx", str(pkt), qos=0
            )
        finally:
            patcher.stop()

    async def test_send_when_not_connected_does_not_raise(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            await t.connect()
            # _connected is False (not yet confirmed by broker)
            await t.send(build_packet("01", "STATE"))
            mock_inst.publish.assert_not_called()
        finally:
            patcher.stop()

    async def test_send_without_connect_does_not_raise(self):
        t = _make()
        await t.send(build_packet("01", "STATE"))  # no client at all


# ---------------------------------------------------------------------------
# paho callbacks
# ---------------------------------------------------------------------------

class TestCallbacks:

    async def test_on_connect_rc0_sets_connected_and_subscribes(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            await t.connect()
            t._on_connect(mock_inst, None, {}, rc=0)
            assert t.connected
            mock_inst.subscribe.assert_called_once_with("dcn/control/rx", qos=0)
        finally:
            patcher.stop()

    async def test_on_connect_nonzero_rc_does_not_set_connected(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            await t.connect()
            t._on_connect(mock_inst, None, {}, rc=5)
            assert not t.connected
        finally:
            patcher.stop()

    async def test_on_disconnect_clears_connected(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            t._connected = True
            t._on_disconnect(mock_inst, None, rc=1)
            assert not t.connected
        finally:
            patcher.stop()

    async def test_on_message_dispatches_valid_packet(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            t._loop = asyncio.get_event_loop()
            received = []
            t.on_packet(lambda p, n: received.append(p))

            msg = MagicMock()
            msg.payload = b"/0001:STATE:XX"
            msg.topic = "dcn/control/rx"
            t._on_message(mock_inst, None, msg)
            await asyncio.sleep(0.05)

            assert len(received) == 1
            assert received[0].payload == "STATE"
            assert received[0].from_addr == "00"
            assert received[0].to_addr == "01"
        finally:
            patcher.stop()

    async def test_on_message_ignores_non_dcn_data(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            t._loop = asyncio.get_event_loop()
            received = []
            t.on_packet(lambda p, n: received.append(p))

            msg = MagicMock()
            msg.payload = b"not a dcn packet"
            msg.topic = "dcn/control/rx"
            t._on_message(mock_inst, None, msg)
            await asyncio.sleep(0.05)

            assert len(received) == 0
        finally:
            patcher.stop()

    async def test_on_message_broadcast_packet(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            t._loop = asyncio.get_event_loop()
            received = []
            t.on_packet(lambda p, n: received.append(p))

            msg = MagicMock()
            msg.payload = b"//ROLLCALL:XX"
            msg.topic = "dcn/control/rx"
            t._on_message(mock_inst, None, msg)
            await asyncio.sleep(0.05)

            assert len(received) == 1
            assert received[0].broadcast

        finally:
            patcher.stop()

    async def test_on_message_strips_whitespace_from_payload(self):
        patcher, _, mock_inst = _mqtt_patch()
        try:
            t = _make()
            t._loop = asyncio.get_event_loop()
            received = []
            t.on_packet(lambda p, n: received.append(p))

            msg = MagicMock()
            msg.payload = b"  /0001:PING:XX  \r\n"
            msg.topic = "dcn/control/rx"
            t._on_message(mock_inst, None, msg)
            await asyncio.sleep(0.05)

            assert len(received) == 1
        finally:
            patcher.stop()
