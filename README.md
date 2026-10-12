# 🏎️ Virtual Sim

[![Platform: Windows](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-blue.svg)](https://microsoft.com/windows)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8+-brightgreen.svg)](https://www.python.org/)
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-red.svg)](https://opencv.org/)
[![ViGEmBus](https://img.shields.io/badge/Driver-ViGEmBus-purple.svg)](https://github.com/nefarius/ViGEmBus)

> A low-latency DIY sim racing controller rig for Windows. Converts webcam foot tracking into analog pedal inputs, pairs with mobile steering via vJoy, and emulates a virtual Xbox 360 controller with an in-game click-through HUD.

---

## Overview

**Virtual Sim** turns everyday hardware into a responsive racing simulator setup without expensive pedals or wheels:

```
┌──────────────────┐      ┌─────────────────────────────┐
│  Webcam Tracker  │ ───► │  Pedal Tracker (OpenCV)     │
│  (Red / Yellow)  │      │  • Color Segmentation & CLAHE│
└──────────────────┘      │  • Adaptive Smoothing       │
                          └──────────────┬──────────────┘
┌──────────────────┐                     │
│  Smartphone      │                     ▼
│  (Monect / vJoy) │ ───► ┌─────────────────────────────┐      ┌───────────────────────┐
│  • Gyro Steering │      │  Virtual Xbox Controller    │ ───► │  Sim / Racing Game    │
│  • Paddle Shifts │      │  (ViGEmBus / vgamepad)      │      │  (Forza, Assetto, etc)│
└──────────────────┘      └──────────────┬──────────────┘      └───────────────────────┘
                                         │
                                         ▼
                          ┌─────────────────────────────┐
                          │  DWM Click-Through HUD      │
                          │  (Always-on-top telemetry)  │
                          └─────────────────────────────┘
```

- **Pedals via Computer Vision**: Tracks your feet using colored markers or socks (Red = Accelerator & Brake; Yellow = Clutch) and translates vertical displacement into analog trigger values.
- **Mobile Steering & Controls**: Reads steering angle, paddle shifts, handbrake, and horn from your smartphone using Monect PC Remote over vJoy.
- **Virtual Xbox 360 Gamepad**: Aggregates all inputs into a native virtual XInput controller recognized by any racing game.
- **Click-Through HUD Overlay**: A hardware-accelerated Win32 DWM layered overlay displaying real-time telemetry over fullscreen and borderless games without stealing input focus.

---

## Features

- **High-Performance Vision Engine**: Runs color segmentation on downscaled frames with CLAHE histogram equalization, keeping CPU usage minimal while preserving high FPS.
- **Dual-Zone Right Foot Tracking**: Automatically splits right-foot motion into accelerator and brake zones with resting threshold detection.
- **Clutch Dropout Protection**: Frame-hold smoothing buffers tracking drops to eliminate sudden accidental disengagements.
- **Batched Gamepad Updates**: State dirty-flagging only updates ViGEmBus when values change, avoiding bus saturation.
- **Zero-Distraction Overlay**: Transparent, click-through HUD rendered with Win32 GDI & OpenCV that sits seamlessly above DirectX games.
- **Interactive 7-Step Calibration**: Calibrate floor height, press depth, and pedal zones in seconds.
- **Built-in Hardware Inspector**: Includes an interactive joystick diagnostics utility to map phone/wheel axes and buttons.

---

## Requirements

### Software
- **Windows 10 / 11** (required for DWM layered windows and ViGEmBus)
- **Python 3.8+**
- **ViGEmBus Driver**: Download and run the installer from the [ViGEmBus Releases](https://github.com/nefarius/ViGEmBus/releases) page.

> [!IMPORTANT]
> The virtual gamepad emulator requires the ViGEmBus system driver. Ensure ViGEmBus is installed before launching the tracker.

### Hardware
- Standard USB webcam or laptop camera pointed toward your foot well / floor.
- Two distinct colored markers or socks:
  - **Red**: Right foot (accelerator & brake)
  - **Yellow**: Left foot (clutch)
- *(Optional)* Smartphone running **Monect PC Remote** with the vJoy driver for steering wheel tilt and button controls.

---

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/MrAnsif/virtual-sim.git
   cd virtual-sim
   ```

2. **Create and activate a virtual environment** *(recommended)*:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install Python dependencies**:
   ```bash
   pip install opencv-python numpy vgamepad pygame
   ```

4. **Verify ViGEmBus installation**:
   Ensure [ViGEmBus](https://github.com/nefarius/ViGEmBus/releases) is installed on your Windows machine.

---

## Quick Start

### 1. Launch the Tracker
Run the main tracker script:
```bash
python pedal_tracker.py
```

If no `pedal_calib.json` is present, the interactive calibration wizard will launch automatically.

### 2. Runtime Keyboard Controls

| Key | Action |
|:---:|:---|
| <kbd>R</kbd> | Launch interactive 7-step recalibration |
| <kbd>P</kbd> | Toggle camera preview and detection debug window |
| <kbd>Q</kbd> | Cleanly shut down tracker, virtual controller, and HUD |

---

## Calibration Guide

The guided setup calibrates pedal boundaries to match your camera angle and foot positions:

| Step | Instruction | Target |
|:---:|:---|:---|
| **1 / 7** | Place both feet flat on the floor | Floor boundary & rest level |
| **2 / 7** | Move right foot to the far right | Accelerator zone horizontal center |
| **3 / 7** | Move right foot toward center | Brake zone horizontal center |
| **4 / 7** | Right foot far right, press pedal down | Full throttle travel depth |
| **5 / 7** | Right foot centered, press pedal down | Full brake travel depth |
| **6 / 7** | Left foot flat, pedal released | Clutch resting position |
| **7 / 7** | Left foot fully pressed down | Full clutch travel depth |

Press <kbd>SPACE</kbd> at each step to save the point, or <kbd>Q</kbd> to skip. Calibration parameters are saved to `pedal_calib.json`.

> [!TIP]
> For best tracking accuracy, ensure even floor lighting and avoid red or bright yellow carpets or background objects within the camera frame.

---

## Controller Input Mapping

The system consolidates vision and mobile inputs into standard Xbox 360 controller signals:

| Vehicle Action | Input Source | Virtual Xbox Mapping | Range / Type |
|:---|:---|:---|:---|
| **Throttle** | Webcam (Red Marker - Right Zone) | **Right Trigger (`RT`)** | `0` – `255` |
| **Brake** | Webcam (Red Marker - Center Zone) | **Left Trigger (`LT`)** | `0` – `255` |
| **Clutch** | Webcam (Yellow Marker - Left Foot) | **Right Stick Y (`RS Up`)** | Threshold `> 80` |
| **Steering** | Monect / vJoy Axis 1 | **Left Stick X (`LS X`)** | `-32768` to `+32767` |
| **Upshift** | Monect Button 0 | **Left Shoulder (`LB`)** | Digital Button |
| **Downshift** | Monect Button 1 | **Right Shoulder (`RB`)** | Digital Button |
| **Handbrake** | Monect Button 2 | **Right Stick Y (`RS Down`)** | Axis Toggle |
| **Horn** | Monect Button 3 | **Right Thumb Click (`RS`)** | Digital Button |

---

## Telemetry HUD Overlay

A lightweight, click-through bar is rendered directly onto your desktop using Windows Desktop Window Manager (`DWM`):

```
┌─────────────────────────────────────────────────────────────┐
│ ST [▬▬|▬▬]  AC [█████ 100%]  BR [░░░░ 0%]  CL [░░░░ 0%]  DN UP HB HR │
└─────────────────────────────────────────────────────────────┘
```

- **Click-Through & Non-Activating**: Uses `WS_EX_LAYERED`, `WS_EX_TRANSPARENT`, and `WS_EX_NOACTIVATE` so mouse clicks pass straight to the game without alt-tabbing or losing control.
- **Bi-directional Steering Bar**: Displays live wheel deflection angle left and right.
- **Pedal Percentages**: Real-time gauge bars for Throttle (`AC`), Brake (`BR`), and Clutch (`CL`).
- **Button Toggles**: Indicators for Downshift (`DN`), Upshift (`UP`), Handbrake (`HB`), and Horn (`HR`).

---

## Diagnostics & Troubleshooting

### Inspecting Joystick Inputs (`monect.py`)
If your smartphone or physical joystick uses different axes or button mappings, run the built-in inspector:

```bash
python monect.py
```

This live console utility monitors all detected joysticks and displays axis values, button states, and POV hats in real-time. Use it to confirm your device index and axis IDs, then update `steering.py` if needed:

```python
# steering.py
STEERING_AXIS     = 1    # Set to your phone's steering axis
DOWNSHIFT_BUTTON  = 1    # Downshift button index
UPSHIFT_BUTTON    = 0    # Upshift button index
HANDBRAKE_BUTTON  = 2    # Handbrake button index
HORN_BUTTON       = 3    # Horn button index
```

### Common Issues

> [!NOTE]
> **Virtual Gamepad Not Detected in Games**
> Ensure the game supports XInput controllers. If the game does not register inputs, launch `pedal_tracker.py` before starting the game.

> [!WARNING]
> **Camera Permission or Open Error**
> If you see `[ERROR] Cannot open camera`, verify that another application is not using the webcam and adjust `CAMERA_INDEX` in `pedal_tracker.py` (e.g., set to `1` or `2` for external USB webcams).
