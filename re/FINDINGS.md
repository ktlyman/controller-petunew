# Reverse Engineering Findings

APK: PetuNew v2.2.26 (`cn.P2PPetCam.www.linyuan`)

## APK Protection

The APK uses **Qihoo 360 Jiagu** packer. The dex bytecode is encrypted at rest
and decrypted only at runtime by `libjiagu.so`. Static decompilation with jadx
only yields the packer stub (`com.stub.StubApp`), not the actual app code.

**Next step**: Runtime dex dump via Android emulator, Frida Gadget injection,
or network capture to observe MQTT traffic directly.

## Confirmed: Three Communication Channels

### Channel 1: TUTK P2P (Camera/Audio)

Native libraries in the APK:
- `libIOTCAPIs.so` — IOTC session management
- `libAVAPIs.so` — Audio/Video streaming + IO Control
- `libTUTKGlobalAPIs.so` — Global TUTK initialization
- `libRDTAPIs.so` — Reliable Data Transfer
- `libsCHL.so` — Secure Channel (DTLS/TLS for P2P encryption)

JNI entry points confirmed in `libAVAPIs.so`:
- `Java_com_tutk_IOTC_AVAPIs_avSendIOCtrl`
- `Java_com_tutk_IOTC_AVAPIs_avRecvIOCtrl`
- `Java_com_tutk_IOTC_AVAPIs_avSendIOCtrlExit`

### Channel 2: MQTT (Feeding Commands)

Evidence from AndroidManifest.xml:
- `org.eclipse.paho.android.service.MqttService` — Eclipse Paho MQTT service
- `cn.P2PPetCam.www.UiV2.mqtt.MyMqttService` — Custom MQTT service
- `org.eclipse.paho.client.mqttv3.spi.NetworkModuleFactory` — Service provider
- Layout resource `ly_device_more_item_mqtt` — MQTT UI elements

The actual MQTT broker URL, topic structure, and message format are locked
inside the encrypted dex. Based on the Petlibro PLAF203 reference (see below),
the MQTT protocol likely follows a similar pattern.

### Channel 3: BLE (Bluetooth Low Energy)

Manifest activities:
- `cn.P2PPetCam.www.UiV2.ble.BleService`
- `cn.P2PPetCam.www.UiV2.acty.LyAddDevByBleActivity`
- `cn.P2PPetCam.www.UiV2.acty.LyAddDevByBleConnectActivity`
- `cn.P2PPetCam.www.UiV2.ble.DevUpgradeActivity` (firmware DFU)
- `cn.P2PPetCam.www.UiV2.acty.LyBleFeedMusicActivity`

BLE is used for device provisioning (WiFi setup), firmware updates (DFU), and
possibly direct feeding commands on some models.

## Device Models

From string resources and manifest activity names:

| Model ID | Product Name | Features |
|----------|-------------|----------|
| FX801 | Camera Pet Feeder | Camera + Feeder |
| FX806 | No Camera Pet Feeder | Feeder only |
| FX901 | Pet Water Feeder | Water fountain |
| 606 | Unknown (PetFun variant) | Has dedicated activities |
| lws36 | Unknown | Has dedicated feed settings |

## Feeding-Related Activities

### PetUNew / "Linyuan" (LY prefix)

- `LyManualFeedSettingActivity` — Manual feed portion/settings
- `LyFeedSettingActivity` — Feed settings
- `LyAutoFeedSettingActivity` — Automatic schedule settings
- `LyAddAutoFeedingActivity` — Add new schedule
- `LyBleFeedMusicActivity` — Feed audio over BLE

### PetFun (petfun prefix)

- `AddAutoFeeding901Activity` — Auto feeding for water feeder (901)
- `Petfun2FeedSetActy` — Feed settings (generic)
- `Petfun2FeedSet901Acty` — Feed settings (901)
- `Petfun2FeedSet806Acty` — Feed settings (806)
- `Petfun2FeedSetLws36Acty` — Feed settings (lws36)
- `PetfunManualFeed2Dialog` — Manual feed dialog
- `PetfunManualFeed2Dialog901` — Manual feed dialog (901)
- `PetfunManualFeedSettingActy901` — Manual feed settings (901)
- `AutoFeedSetting901Activity` — Auto feed settings (901)

### MCO / Skymee

- `McoAutoFeedingActivity` — Auto feeding
- `McoAutoFeedSettingActivity` — Feed schedule settings
- `McoOwlPlayAfterFeed` — Play after feeding
- `McoLiveViewPetFeederActivity` — Live view for feeder

### Legacy / Generic

- `ManualFeedSettingActivity` — Manual feed
- `ManualFeedDialog` — Manual feed dialog
- `AutoFeedSettingActivity` — Auto feed settings
- `AddAutoFeedingActivity` — Add schedule
- `FeedSettingActivity` — Feed settings

## Brand Connections

| Brand | Domain/Contact | Platform |
|-------|---------------|----------|
| PetUNew/PetU | petusound.com, PetU-service@outlook.com | Primary |
| DrFeeder | DrFeeder@goldstore.com, drfeeder namespace | Same app |
| Skymee/MCO | skymee.com, en.skymee.com | Same app |
| PetFun | cn.P2PPetCam.www (base namespace) | Same app |
| WOPET | wopet references in resources | Same hardware |

The app `cn.P2PPetCam.www.linyuan` is a multi-brand white-label platform
from "Jk" organization (Guangzhou, China) that serves PetUNew, PetFun,
DrFeeder, Skymee/MCO, and WOPET devices.

## Petlibro PLAF203 Reference (icex2/plaf203)

The Petlibro PLAF203 is the only fully reverse-engineered TUTK pet feeder+camera.
It confirms the dual-channel architecture and provides the MQTT protocol reference.

### MQTT Protocol

**Broker**: `mqtt.us.petlibro.com:1883` (unencrypted)
**Auth**: Device serial as client ID, factory credentials for user/pass
**Topic pattern**: `dl/plaf203/{DEVICE_ID}/device/{CHANNEL}/{DIRECTION}`

Channels: `heart`, `ota`, `ntp`, `broadcast`, `config`, `event`, `service`, `system`
Directions: `sub` (server-to-device), `post` (device-to-server)

### Message Envelope

```json
{
    "cmd": "COMMAND_NAME",
    "msgId": "sha256_of_uuid4_first_32_chars",
    "ts": 1234567890000
}
```

### Feeding Commands

**Manual feed**: `MANUAL_FEEDING_SERVICE` via `service/sub`
```json
{"cmd": "MANUAL_FEEDING_SERVICE", "msgId": "...", "ts": ..., "grainNum": 50}
```

**Feed completion event**: `GRAIN_OUTPUT_EVENT` via `event/post`
```json
{
    "cmd": "GRAIN_OUTPUT_EVENT",
    "finished": true,
    "type": 2,
    "actualGrainNum": 50,
    "expectedGrainNum": 50,
    "execStep": 2,
    "planId": null
}
```
Types: 1=FEED_PLAN, 2=MANUAL_FEED, 3=MANUAL_FEED_BUTTON
ExecSteps: 1=GRAIN_START, 2=GRAIN_END, 3=GRAIN_BLOCKING

**Feeding schedules**: `FEEDING_PLAN_SERVICE` via `service/sub`
```json
{
    "cmd": "FEEDING_PLAN_SERVICE",
    "plans": [{
        "planId": 1,
        "executionTime": "19:00",
        "repeatDay": [1, 2, 3, 4, 5, 6, 7],
        "grainNum": 3,
        "enableAudio": false,
        "audioTimes": 1
    }]
}
```

**Get schedules**: Device sends `GET_FEEDING_PLAN_EVENT` via `event/post`,
server responds with plans on `event/sub`.

**No dedicated history command** — feeding history is built from
`GRAIN_OUTPUT_EVENT` events.

### TUTK Provisioning over MQTT

The MQTT channel provisions TUTK camera access:
```json
{
    "cmd": "TUTK_CONTRACT_SERVICE",
    "deviceTutkToken": "...",
    "deviceTutkUrl": "https://tutk.endpoint",
    "contractId": "...",
    "startTime": "...",
    "expires": "..."
}
```

### All 30 Petlibro MQTT Commands

```
ATTR_GET_SERVICE         ATTR_PUSH_EVENT          ATTR_SET_SERVICE
BINDING                  DETECTION_EVENT          DEVICE_FEEDING_PLAN_SERVICE
DEVICE_INFO_SERVICE      DEVICE_PROPERTIES_SERVICE DEVICE_REBOOT
DEVICE_START_EVENT       ERROR_EVENT              FEEDING_PLAN_SERVICE
GET_CONFIG               GET_FEEDING_PLAN_EVENT   GRAIN_OUTPUT_EVENT
HEARTBEAT                INITIALIZE_SD_CARD_SERVICE MANUAL_FEEDING_SERVICE
NTP                      NTP_SYNC                 OTA_INFORM
OTA_PROGRESS             OTA_UPGRADE              RESET
RESTORE                  SERVER_CONFIG_PUSH       TUTK_CONTRACT_SERVICE
UNBIND                   WIFI_CHANGE_SERVICE      WIFI_RECONNECT_SERVICE
```

## Next Steps

### Priority 1: Network Capture (Best path without rooted device)

Set up a laptop WiFi hotspot, re-provision the feeder to connect through it,
and capture all traffic with Wireshark/tcpdump:

```bash
# Capture TUTK P2P (UDP)
sudo tcpdump -i <hotspot-iface> -s 0 -w tutk.pcap \
    'udp and (port 10000 or port 10001 or port 32761)'

# Capture MQTT (TCP)
sudo tcpdump -i <hotspot-iface> -s 0 -w mqtt.pcap \
    'tcp and (port 1883 or port 8883)'

# Capture all (comprehensive)
sudo tcpdump -i <hotspot-iface> -s 0 -w all.pcap \
    'host <feeder-ip>'
```

Then trigger:
1. Manual feed from the app
2. Add/modify a feeding schedule
3. Camera snapshot

Analyze the MQTT traffic in Wireshark to discover:
- Broker hostname and port
- Topic structure
- Message format
- Authentication credentials

### Priority 2: Android Emulator Runtime Dump

Run the APK in an Android emulator with root, dump the decrypted dex:
1. Install Android Studio + emulator (rooted image)
2. Install the APK
3. After launch, copy `/data/data/cn.P2PPetCam.www.linyuan/.jiagu/*.dex`
4. Decompile the dumped dex with jadx

### Priority 3: Older APK Version

Try APK versions before v2.1.x — they may not have 360 Jiagu protection.
Earlier versions might use ProGuard only (which jadx handles well).
