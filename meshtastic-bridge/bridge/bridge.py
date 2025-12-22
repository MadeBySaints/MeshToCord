#!/usr/bin/env python3
"""
Meshtastic MQTT to Discord Bridge
Forwards mesh messages from MQTT broker to Discord channel
Separate webhook for telemetry, position, and nodeinfo updates
"""

import os
import json
import logging
from datetime import datetime
import paho.mqtt.client as mqtt
from discord_webhook import DiscordWebhook, DiscordEmbed

# Configuration
MQTT_BROKER = os.getenv('MQTT_BROKER', 'localhost')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_TOPIC = os.getenv('MQTT_TOPIC', 'meshtastic/#')
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')
DISCORD_TELEMETRY_WEBHOOK_URL = os.getenv('DISCORD_TELEMETRY_WEBHOOK_URL', '')

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Track seen message IDs to prevent duplicates
seen_messages = set()
MAX_SEEN_MESSAGES = 1000

# Node name cache: node_id (hex like !9e9d5748) → names
node_names = {}

def update_node_name(node_id: str, short_name: str = None, long_name: str = None):
    """Update cached names for a node"""
    if node_id not in node_names:
        node_names[node_id] = {}
    
    if short_name:
        node_names[node_id]['short'] = short_name
    if long_name:
        node_names[node_id]['long'] = long_name
    
    logger.debug(f"Name cache updated for {node_id}: {node_names[node_id]}")

def get_node_display_name(node_id: str) -> str:
    """Return the best available name for a node (long → short → ID)"""
    if node_id in node_names:
        names = node_names[node_id]
        if names.get('long'):
            return names['long']
        if names.get('short'):
            return names['short']
    return node_id  # fallback to hex ID


def send_to_discord(message_data: dict):
    """Send text messages to the main Discord webhook"""
    if not DISCORD_WEBHOOK_URL:
        logger.error("Main Discord webhook URL not configured!")
        return

    try:
        webhook = DiscordWebhook(url=DISCORD_WEBHOOK_URL, rate_limit_retry=True)
        embed = DiscordEmbed(title="📡 Mesh Message", color='03b2f8')

        # From
        if 'from' in message_data:
            display = message_data['from']
            if 'from_id' in message_data and message_data['from_id'] != display:
                display = f"{display} ({message_data['from_id']})"
            embed.add_embed_field(name="From", value=display, inline=False)

        # Channel
        if 'channel' in message_data:
            embed.add_embed_field(name="Channel", value=f"#{message_data['channel']}", inline=False)

        # Signal
        signal = []
        if message_data.get('rssi') is not None:
            signal.append(f"RSSI: {message_data['rssi']} dBm")
        if message_data.get('snr') is not None:
            signal.append(f"SNR: {message_data['snr']} dB")
        if signal:
            embed.add_embed_field(name="Signal", value=" | ".join(signal), inline=False)

        # Text
        if 'text' in message_data:
            embed.add_embed_field(name="Message", value=message_data['text'], inline=False)

        # Footer
        if 'topic' in message_data:
            embed.set_footer(text=f"Topic: {message_data['topic']}")

        webhook.add_embed(embed)
        webhook.execute()
        logger.info("Text message sent to main Discord webhook")
    except Exception as e:
        logger.error(f"Failed to send text message: {e}")


def send_telemetry_to_discord(message_data: dict):
    """Send position/telemetry/nodeinfo to the dedicated telemetry webhook"""
    if not DISCORD_TELEMETRY_WEBHOOK_URL:
        logger.warning("Telemetry webhook not configured – skipping telemetry/position/nodeinfo")
        return

    try:
        webhook = DiscordWebhook(url=DISCORD_TELEMETRY_WEBHOOK_URL, rate_limit_retry=True)
        msg_type = message_data.get('type', 'unknown')

        # Title & colour
        titles = {
            'position': ("📍 Position Update", '42f554'),
            'telemetry': ("📊 Telemetry Update", 'f5a742'),
            'nodeinfo': ("ℹ️ Node Info Update", '4287f5'),
        }
        title, color = titles.get(msg_type, (f"📡 {msg_type.title()}", '808080'))
        embed = DiscordEmbed(title=title, color=color)

        # From (original node)
        if 'from' in message_data:
            display = message_data['from']
            if 'from_id' in message_data and message_data['from_id'] != display:
                display = f"{display} ({message_data['from_id']})"
            embed.add_embed_field(name="From", value=display, inline=False)

        payload = message_data.get('payload', {})

        # Position
        if msg_type == 'position':
            pos = payload.get('position', payload)
            lat_i = pos.get('latitude_i') or pos.get('latitudeI')
            lon_i = pos.get('longitude_i') or pos.get('longitudeI')

            if lat_i is not None and lon_i is not None and (lat_i != 0 or lon_i != 0):
                lat = lat_i / 10_000_000.0
                lon = lon_i / 10_000_000.0
                embed.add_embed_field(name="Location", value=f"{lat:.6f}, {lon:.6f}", inline=False)
                embed.add_embed_field(name="Map", value=f"[Open in Google Maps](https://maps.google.com/?q={lat},{lon})", inline=False)

            if pos.get('altitude') is not None:
                embed.add_embed_field(name="Altitude", value=f"{pos['altitude']} m", inline=True)

            sats = pos.get('sats_in_view') or pos.get('satsInView')
            if sats is not None:
                embed.add_embed_field(name="Satellites", value=str(sats), inline=True)

        # Telemetry (device metrics)
        elif msg_type == 'telemetry':
            metrics = payload.get('device_metrics', payload)

            if metrics.get('battery_level') is not None:
                battery = metrics['battery_level']
                emoji = '🔋' if battery > 20 else '🪫'
                embed.add_embed_field(name="Battery", value=f"{emoji} {battery}%", inline=True)

            if metrics.get('voltage') is not None:
                embed.add_embed_field(name="Voltage", value=f"{metrics['voltage']:.2f} V", inline=True)

            if metrics.get('channel_utilization') is not None:
                embed.add_embed_field(name="Channel Utilization", value=f"{metrics['channel_utilization']:.1f}%", inline=True)

            if metrics.get('air_util_tx') is not None:
                embed.add_embed_field(name="Air Util TX", value=f"{metrics['air_util_tx']:.2f}%", inline=True)

        # Nodeinfo
        elif msg_type == 'nodeinfo':
            user = payload.get('user', payload)

            long_name = user.get('longName') or user.get('longname')
            if long_name:
                embed.add_embed_field(name="Long Name", value=long_name, inline=False)
                if 'from_id' in message_data:
                    update_node_name(message_data['from_id'], long_name=long_name)

            short_name = user.get('shortName') or user.get('shortname')
            if short_name:
                embed.add_embed_field(name="Short Name", value=short_name, inline=True)
                if 'from_id' in message_data:
                    update_node_name(message_data['from_id'], short_name=short_name)

            hw = user.get('hwModel') or user.get('hardwareModel') or payload.get('hardwareModel')
            if hw is not None:
                embed.add_embed_field(name="Hardware", value=str(hw), inline=True)

            fw = payload.get('firmware_version') or payload.get('firmwareVersion')
            if fw:
                embed.add_embed_field(name="Firmware", value=fw, inline=True)

        # Signal (common to all)
        signal = []
        if message_data.get('rssi') is not None:
            signal.append(f"RSSI: {message_data['rssi']} dBm")
        if message_data.get('snr') is not None:
            signal.append(f"SNR: {message_data['snr']} dB")
        if signal:
            embed.add_embed_field(name="Signal", value=" | ".join(signal), inline=False)

        # Timestamp footer
        if 'timestamp' in message_data:
            ts = datetime.fromtimestamp(message_data['timestamp'])
            embed.set_footer(text=f"Time: {ts.strftime('%Y-%m-%d %H:%M:%S')}")

        webhook.add_embed(embed)
        webhook.execute()
        logger.info(f"{msg_type.capitalize()} sent to telemetry webhook from {message_data.get('from', 'unknown')}")
    except Exception as e:
        logger.error(f"Failed to send {msg_type} to telemetry webhook: {e}")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker")
        client.subscribe(MQTT_TOPIC)
        logger.info(f"Subscribed to {MQTT_TOPIC}")
    else:
        logger.error(f"MQTT connect failed (code {rc})")


def parse_meshtastic_message(topic: str, payload_bytes: bytes) -> dict | None:
    """Parse a Meshtastic JSON MQTT message and return a cleaned dict"""
    try:
        data = json.loads(payload_bytes)
        msg = {'topic': topic}

        msg_type = data.get('type', 'unknown')
        msg['type'] = msg_type

        if 'id' in data:
            msg['id'] = data['id']
        if 'timestamp' in data:
            msg['timestamp'] = data['timestamp']

        # === CRITICAL FIX: Always use the ORIGINAL node ('from') for display and caching ===
        if 'from' in data:
            from_hex = f"!{data['from']:08x}"
            msg['from_id'] = from_hex
            msg['from'] = get_node_display_name(from_hex)
        elif 'sender' in data:  # rare fallback
            msg['from_id'] = data['sender']
            msg['from'] = get_node_display_name(data['sender'])
        else:
            logger.warning("Message has no 'from' or 'sender' field")
            return None

        # Channel from topic (e.g., meshtastic/json/0/text → channel 0)
        parts = topic.split('/')
        if len(parts) >= 4:
            msg['channel'] = parts[3]

        # Full payload for telemetry/position/nodeinfo
        if 'payload' in data:
            msg['payload'] = data['payload']

        # Text messages
        if msg_type == 'text':
            if isinstance(data.get('payload'), dict) and 'text' in data['payload']:
                msg['text'] = data['payload']['text']
            elif 'text' in data:
                msg['text'] = data['text']
            else:
                logger.debug("Empty text message – skipping")
                return None

        # Signal strength
        if 'rssi' in data:
            msg['rssi'] = data['rssi']
        if 'snr' in data:
            msg['snr'] = data['snr']

        # Cache node names as soon as we see a nodeinfo packet (uses correct 'from')
        if msg_type == 'nodeinfo':
            user = data.get('payload', {}).get('user', {})
            update_node_name(
                msg['from_id'],
                short_name=user.get('shortName') or user.get('shortname'),
                long_name=user.get('longName') or user.get('longname')
            )

        return msg

    except Exception as e:
        logger.error(f"Parse error: {e}")
        return None


def on_message(client, userdata, msg):
    if '/json/' not in msg.topic:
        return  # ignore encrypted/binary topics

    parsed = parse_meshtastic_message(msg.topic, msg.payload)
    if not parsed:
        return

    # Duplicate prevention
    if 'id' in parsed:
        msg_id = parsed['id']
        if msg_id in seen_messages:
            logger.info(f"Duplicate message skipped (ID {msg_id})")
            return
        seen_messages.add(msg_id)
        if len(seen_messages) > MAX_SEEN_MESSAGES:
            seen_messages.pop()  # remove oldest

    msg_type = parsed.get('type', 'unknown')
    logger.info(f"Processed {msg_type} from {parsed.get('from', 'unknown')}")

    if msg_type == 'text':
        send_to_discord(parsed)
    elif msg_type in {'position', 'telemetry', 'nodeinfo'}:
        send_telemetry_to_discord(parsed)
    else:
        logger.debug(f"Ignored message type: {msg_type}")


def main():
    if not DISCORD_WEBHOOK_URL:
        logger.error("DISCORD_WEBHOOK_URL is required!")
        return

    logger.info("Starting Meshtastic → Discord bridge")
    client = mqtt.Client(client_id="meshtastic-discord-bridge-v2")
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()