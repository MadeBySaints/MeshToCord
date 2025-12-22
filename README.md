# MeshToCord
**Meshtastic → Discord Bridge**

MeshToCord is a lightweight bridge that forwards **public Meshtastic messages** from a node you control directly to a **Discord server** using webhooks.

It listens to Meshtastic traffic via **MQTT (JSON output)** and posts messages to Discord in near real-time.

---

## Features

- 📡 Forwards public Meshtastic messages
- 🔁 Uses MQTT with JSON output
- 💬 Sends messages to Discord via webhook
- 🐳 Runs entirely in Docker
- 🧠 Minimal configuration required

---

## Requirements

### Hardware
- Meshtastic-compatible node with WiFi support

### Software
- Docker
- Docker Compose
- MQTT broker (Docker or external)
- Discord server with a webhook URL

---

## Meshtastic Device Configuration

Configure your Meshtastic node as follows:

### LoRa
Ok to MQTT = True  
Transmit Enabled = True  

### Device
Role = ROUTER  
Rebroadcast Mode = CORE_PORTNUMS_ONLY  

### Network
WiFi Enabled = True  
SSID = <your_wifi_ssid>  
Password = <your_wifi_password>  
UDP Config = Enabled  

### MQTT
Address = <MQTT_BROKER_IP>:1883  
Username = (leave blank)  
Password = (leave blank)  
Encryption Enabled = False  
JSON Output Enabled = True  
Root Topic = Meshtastic  

Device setup complete.

---

## Docker Setup

### 1. Clone the Repository

git clone https://github.com/<your-username>/MeshToCord.git  
cd MeshToCord/meshtastic-bridge  

---

### 2. Configure Environment Variables

Edit the .env file and add your Discord webhook URL:

DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/XXXXXXXX

Keep webhook URLs private.

---

### 3. Build and Start the Container

docker-compose up -d --build

This will:
- Connect to your MQTT broker
- Subscribe to Meshtastic topics
- Forward public mesh messages to Discord

---

## Verification

1. Send a public message from any node on your mesh  
2. Check your Discord channel  
3. Messages should appear almost instantly  

---

## Troubleshooting

If no messages appear:
- Verify JSON Output Enabled = True
- Confirm MQTT broker IP and port
- Ensure device role is ROUTER
- Confirm Ok to MQTT = True

Check container logs:

docker logs meshtastic-bridge

---

## Security Notes

- Only public mesh messages are forwarded
- MQTT encryption is disabled by design
- Do not expose your MQTT broker to the public internet
- Treat Discord webhook URLs as secrets

---

## License

MIT License  
Free to use, modify, and distribute.
