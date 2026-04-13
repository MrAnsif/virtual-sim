"""
=============================================================
  FOOT PEDAL TRACKER
  Maps webcam foot detection → Virtual Xbox controller
  Red marker  = Right foot (Accelerator / Brake)
  Yellow marker = Left foot (Clutch)
=============================================================

REQUIREMENTS:
    pip install opencv-python numpy vgamepad pygame

ALSO INSTALL:
    ViGEmBus driver — https://github.com/nefarius/ViGEmBus/releases
    (Required for vgamepad to create virtual controller)

CONTROLS DURING RUN:
    R — Recalibrate
    P — Toggle preview window
    Q — Quit
=============================================================
"""

import cv2
import numpy as np
import vgamepad as vg
import json
import os
import time
from steering import SteeringInput

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────

PREVIEW         = True
CAMERA_INDEX    = 0
TARGET_FPS      = 30
CALIB_FILE      = "pedal_calib.json"

SMOOTHING       = 0.55
ZONE_DEAD_BAND  = 30
MIN_BLOB_AREA   = 300

# ─────────────────────────────────────────────
#  HSV COLOR RANGES
# ─────────────────────────────────────────────

RED_LOWER_1 = np.array([145, 120, 120])
RED_UPPER_1 = np.array([165, 255, 255])
RED_LOWER_2 = np.array([145, 120, 120])
RED_UPPER_2 = np.array([165, 255, 255])

YELLOW_LOWER = np.array([18, 100, 100])
YELLOW_UPPER = np.array([38, 255, 255])

# ─────────────────────────────────────────────
#  CALIBRATION DEFAULT
# ─────────────────────────────────────────────

DEFAULT_CALIB = {
    "floor_y":          400,
    "accel_zone_x":     450,
    "brake_zone_x":     250,
    "accel_press_y":    350,
    "brake_press_y":    350,
    "clutch_rest_y":    300,
    "clutch_press_y":   400,
    "frame_width":      640,
    "frame_height":     480
}

# ─────────────────────────────────────────────
#  UTILITY FUNCTIONS
# ─────────────────────────────────────────────

def map_value(val, in_min, in_max, out_min, out_max):
    if in_max == in_min:
        return out_min
    ratio = (val - in_min) / (in_max - in_min)
    ratio = max(0.0, min(1.0, ratio))
    return int(out_min + ratio * (out_max - out_min))


def get_blob_centroid(mask):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    if area < MIN_BLOB_AREA:
        return None
    M = cv2.moments(largest)
    if M["m00"] == 0:
        return None
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    return cx, cy, area, largest


def detect_color(frame_hsv, color):
    if color == "red":
        m1 = cv2.inRange(frame_hsv, RED_LOWER_1, RED_UPPER_1)
        m2 = cv2.inRange(frame_hsv, RED_LOWER_2, RED_UPPER_2)
        mask = cv2.bitwise_or(m1, m2)
    else:
        mask = cv2.inRange(frame_hsv, YELLOW_LOWER, YELLOW_UPPER)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return get_blob_centroid(mask), mask


def load_calibration():
    if os.path.exists(CALIB_FILE):
        with open(CALIB_FILE, "r") as f:
            print("[INFO] Calibration loaded from file.")
            return json.load(f)
    print("[INFO] No calibration file found. Using defaults.")
    return DEFAULT_CALIB.copy()


def save_calibration(calib):
    with open(CALIB_FILE, "w") as f:
        json.dump(calib, f, indent=2)
    print("[INFO] Calibration saved.")


# ─────────────────────────────────────────────
#  CALIBRATION ROUTINE
# ─────────────────────────────────────────────

def run_calibration(cap):
    print("\n[CALIBRATION STARTED]")
    calib = {}

    ret, frame = cap.read()
    h, w = frame.shape[:2]
    calib["frame_width"]  = w
    calib["frame_height"] = h

    steps = [
        ("floor_y + zones", "Step 1/7: Both feet FLAT on floor, resting position.\n         SPACE to capture."),
        ("accel_zone_x",    "Step 2/7: Right foot angled FAR RIGHT (accelerator position).\n         SPACE to capture."),
        ("brake_zone_x",    "Step 3/7: Right foot CENTERED / straight (brake position).\n         SPACE to capture."),
        ("accel_press_y",   "Step 4/7: Right foot FAR RIGHT, toe FULLY pressed down.\n         SPACE to capture."),
        ("brake_press_y",   "Step 5/7: Right foot CENTERED, toe FULLY pressed down.\n         SPACE to capture."),
        ("clutch_rest_y",   "Step 6/7: Left foot FLAT, clutch RELEASED.\n         SPACE to capture."),
        ("clutch_press_y",  "Step 7/7: Left foot toe FULLY pressed down (clutch engaged).\n         SPACE to capture."),
    ]

    captured = {}

    for key, instruction in steps:
        print(f"\n{instruction}")
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            frame = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            red_blob,    _ = detect_color(hsv, "red")
            yellow_blob, _ = detect_color(hsv, "yellow")

            display = frame.copy()

            if red_blob:
                cx, cy, area, cnt = red_blob
                cv2.drawContours(display, [cnt], -1, (0, 0, 255), 2)
                cv2.circle(display, (cx, cy), 6, (0, 0, 255), -1)
                cv2.putText(display, f"RED ({cx},{cy})", (cx+10, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)

            if yellow_blob:
                cx, cy, area, cnt = yellow_blob
                cv2.drawContours(display, [cnt], -1, (0, 255, 255), 2)
                cv2.circle(display, (cx, cy), 6, (0, 255, 255), -1)
                cv2.putText(display, f"YLW ({cx},{cy})", (cx+10, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1)

            for i, line in enumerate(instruction.split("\n")):
                cv2.putText(display, line.strip(), (10, 30 + i*25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
            cv2.putText(display, "SPACE = Capture | Q = Skip step",
                        (10, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)

            cv2.imshow("Calibration", display)
            k = cv2.waitKey(1) & 0xFF

            if k == ord(' '):
                if red_blob:
                    captured["red_cx"], captured["red_cy"] = red_blob[0], red_blob[1]
                if yellow_blob:
                    captured["yellow_cx"], captured["yellow_cy"] = yellow_blob[0], yellow_blob[1]

                if key == "floor_y + zones":
                    ys = []
                    if red_blob:    ys.append(red_blob[1])
                    if yellow_blob: ys.append(yellow_blob[1])
                    calib["floor_y"] = max(ys) + 20 if ys else h - 20
                    print(f"  floor_y = {calib['floor_y']}")
                elif key == "accel_zone_x":
                    calib["accel_zone_x"] = captured.get("red_cx", w * 0.7)
                    print(f"  accel_zone_x = {calib['accel_zone_x']}")
                elif key == "brake_zone_x":
                    calib["brake_zone_x"] = captured.get("red_cx", w * 0.4)
                    print(f"  brake_zone_x = {calib['brake_zone_x']}")
                elif key == "accel_press_y":
                    calib["accel_press_y"] = captured.get("red_cy", h * 0.8)
                    print(f"  accel_press_y = {calib['accel_press_y']}")
                elif key == "brake_press_y":
                    calib["brake_press_y"] = captured.get("red_cy", h * 0.8)
                    print(f"  brake_press_y = {calib['brake_press_y']}")
                elif key == "clutch_rest_y":
                    calib["clutch_rest_y"] = captured.get("yellow_cy", h * 0.5)
                    print(f"  clutch_rest_y = {calib['clutch_rest_y']}")
                elif key == "clutch_press_y":
                    calib["clutch_press_y"] = captured.get("yellow_cy", h * 0.85)
                    print(f"  clutch_press_y = {calib['clutch_press_y']}")

                break

            elif k == ord('q'):
                print("  Step skipped.")
                break

    cv2.destroyWindow("Calibration")
    save_calibration(calib)
    return calib


# ─────────────────────────────────────────────
#  PREVIEW OVERLAY DRAWING
# ─────────────────────────────────────────────

def draw_preview(frame, calib, state):
    h, w = frame.shape[:2]
    overlay = frame.copy()

    ax = int(calib.get("accel_zone_x", w * 0.35))
    bx = int(calib.get("brake_zone_x", w * 0.70))
    floor_y = int(calib.get("floor_y", h - 20))

    cv2.rectangle(overlay, (0,  0), (ax, floor_y), (0, 80, 0),   -1)
    cv2.rectangle(overlay, (ax, 0), (bx, floor_y), (0, 0, 80),   -1)
    cv2.rectangle(overlay, (bx, 0), (w,  floor_y), (50, 50, 50), -1)
    cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)

    cv2.line(frame, (ax, 0), (ax, floor_y), (0, 255, 0),  2)
    cv2.line(frame, (bx, 0), (bx, floor_y), (0, 80, 255), 2)
    cv2.line(frame, (0, floor_y), (w, floor_y), (255, 255, 0), 2)

    cv2.putText(frame, "FLOOR",       (5, floor_y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,0),   1)
    cv2.putText(frame, "ACCEL ZONE",  (5,          20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0),     1)
    cv2.putText(frame, "BRAKE ZONE",  (ax + 5,     20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,100,255),   1)
    cv2.putText(frame, "CLUTCH AREA", (bx + 5,     20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150,150,150), 1)

    if state["red_blob"]:
        cx, cy, _, cnt = state["red_blob"]
        cv2.drawContours(frame, [cnt], -1, (0, 0, 255), 2)
        cv2.circle(frame, (cx, cy), 8, (0, 0, 255), -1)
        cv2.putText(frame, f"R.FOOT | {state['active_pedal']}",
                    (cx + 10, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,0,255), 2)
        cv2.putText(frame, f"X:{cx} Y:{cy}",
                    (cx + 10, cy + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200,100,100), 1)

    if state["yellow_blob"]:
        cx, cy, _, cnt = state["yellow_blob"]
        cv2.drawContours(frame, [cnt], -1, (0, 255, 255), 2)
        cv2.circle(frame, (cx, cy), 8, (0, 255, 255), -1)
        cv2.putText(frame, "L.FOOT | CLUTCH",
                    (cx + 10, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,255), 2)
        cv2.putText(frame, f"X:{cx} Y:{cy}",
                    (cx + 10, cy + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100,200,200), 1)

    # ── HUD bars
    hud_x, hud_y = 10, h - 180
    bar_w, bar_h = 150, 18
    gap = 26

    def draw_bar(label, value_0_255, color, y_off):
        pct    = value_0_255 / 255.0
        filled = int(bar_w * pct)
        cv2.rectangle(frame, (hud_x, hud_y + y_off),
                      (hud_x + bar_w, hud_y + y_off + bar_h), (50,50,50), -1)
        cv2.rectangle(frame, (hud_x, hud_y + y_off),
                      (hud_x + filled, hud_y + y_off + bar_h), color, -1)
        cv2.rectangle(frame, (hud_x, hud_y + y_off),
                      (hud_x + bar_w, hud_y + y_off + bar_h), (180,180,180), 1)
        cv2.putText(frame, f"{label}: {int(pct*100)}%",
                    (hud_x + bar_w + 8, hud_y + y_off + 13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    draw_bar("ACCEL",  state["accel"],  (0, 220, 0),   0)
    draw_bar("BRAKE",  state["brake"],  (0, 80, 255),  gap)
    draw_bar("CLUTCH", state["clutch"], (0, 220, 220), gap * 2)

    # ── Steering bar (bi-directional)
    steer_y_off = gap * 3
    steer_val   = state.get("steering", 0)
    center_x    = hud_x + bar_w // 2
    pct_steer   = steer_val / 32767.0
    fill_len    = int((bar_w // 2) * abs(pct_steer))
    direction   = "L" if pct_steer < 0 else "R"

    cv2.rectangle(frame, (hud_x, hud_y + steer_y_off),
                  (hud_x + bar_w, hud_y + steer_y_off + bar_h), (50,50,50), -1)
    if pct_steer < 0:
        cv2.rectangle(frame, (center_x - fill_len, hud_y + steer_y_off),
                      (center_x, hud_y + steer_y_off + bar_h), (0, 165, 255), -1)
    else:
        cv2.rectangle(frame, (center_x, hud_y + steer_y_off),
                      (center_x + fill_len, hud_y + steer_y_off + bar_h), (255, 200, 0), -1)
    cv2.line(frame, (center_x, hud_y + steer_y_off),
             (center_x, hud_y + steer_y_off + bar_h), (255,255,255), 1)
    cv2.rectangle(frame, (hud_x, hud_y + steer_y_off),
                  (hud_x + bar_w, hud_y + steer_y_off + bar_h), (180,180,180), 1)
    cv2.putText(frame, f"STEER: {direction} {int(abs(pct_steer)*100)}%",
                (hud_x + bar_w + 8, hud_y + steer_y_off + 13),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200,200,100), 1)

    # ── Gear shift buttons
    btn_y_off = gap * 4
    down_col  = (0, 200, 255) if state.get("downshift") else (60, 60, 60)
    up_col    = (0, 255, 100) if state.get("upshift")   else (60, 60, 60)
    cv2.rectangle(frame, (hud_x,          hud_y + btn_y_off),
                  (hud_x + 68,            hud_y + btn_y_off + bar_h), down_col, -1)
    cv2.rectangle(frame, (hud_x + 76,     hud_y + btn_y_off),
                  (hud_x + bar_w,         hud_y + btn_y_off + bar_h), up_col,   -1)
    cv2.putText(frame, "DN SHIFT",
                (hud_x + 4,       hud_y + btn_y_off + 13),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,0), 1)
    cv2.putText(frame, "UP SHIFT",
                (hud_x + 80,      hud_y + btn_y_off + 13),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,0), 1)

    cv2.putText(frame, f"FPS: {state['fps']:.1f}",
                (w - 90, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
    cv2.putText(frame, "R=Recalib  P=Toggle Preview  Q=Quit",
                (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150,150,150), 1)

    return frame


# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────

def main():
    global PREVIEW

    print("=" * 55)
    print("  FOOT PEDAL TRACKER — Starting")
    print("=" * 55)

    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS,          TARGET_FPS)

    if not cap.isOpened():
        print("[ERROR] Cannot open camera. Check CAMERA_INDEX.")
        return

    calib = load_calibration()
    if not os.path.exists(CALIB_FILE):
        print("[INFO] Running first-time calibration...")
        calib = run_calibration(cap)

    # Init steering input
    steering = SteeringInput()

    # Init virtual gamepad
    try:
        gamepad = vg.VX360Gamepad()
        print("[INFO] Virtual Xbox controller created.")
    except Exception as e:
        print(f"[ERROR] Could not create virtual gamepad: {e}")
        print("        Make sure ViGEmBus driver is installed.")
        cap.release()
        steering.close()
        return

    smooth_accel  = 0.0
    smooth_brake  = 0.0
    smooth_clutch = 0.0

    state = {
        "red_blob":     None,
        "yellow_blob":  None,
        "active_pedal": "NONE",
        "accel":        0,
        "brake":        0,
        "clutch":       0,
        "steering":     0,
        "downshift":    False,
        "upshift":      False,
        "fps":          0.0,
    }

    fps_timer  = time.time()
    fps_frames = 0
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    print("[INFO] Running. Press Q to quit, R to recalibrate, P to toggle preview.")
    print()

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WARN] Frame read failed. Retrying...")
            continue

        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b_ch = cv2.split(lab)
        l = clahe.apply(l)
        frame = cv2.cvtColor(cv2.merge([l, a, b_ch]), cv2.COLOR_LAB2BGR)

        h, w = frame.shape[:2]
        roi_top = int(h * 0.35)
        roi = frame[roi_top:h, 0:w]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        red_result,    _ = detect_color(hsv, "red")
        yellow_result, _ = detect_color(hsv, "yellow")

        red_blob    = None
        yellow_blob = None

        if red_result:
            cx, cy, area, cnt = red_result
            cy_full  = cy + roi_top
            cnt_full = cnt + np.array([[[0, roi_top]]])
            red_blob = (cx, cy_full, area, cnt_full)

        if yellow_result:
            cx, cy, area, cnt = yellow_result
            cy_full  = cy + roi_top
            cnt_full = cnt + np.array([[[0, roi_top]]])
            yellow_blob = (cx, cy_full, area, cnt_full)

        floor_y        = calib.get("floor_y",        h - 20)
        accel_zone_x   = calib.get("accel_zone_x",   int(w * 0.7))
        brake_zone_x   = calib.get("brake_zone_x",   int(w * 0.4))
        accel_press_y  = calib.get("accel_press_y",  int(h * 0.85))
        brake_press_y  = calib.get("brake_press_y",  int(h * 0.85))
        clutch_rest_y  = calib.get("clutch_rest_y",  int(h * 0.55))
        clutch_press_y = calib.get("clutch_press_y", int(h * 0.85))

        raw_accel    = 0
        raw_brake    = 0
        active_pedal = "NONE"

        if red_blob:
            rx, ry = red_blob[0], red_blob[1]
            rest_y = floor_y - 180

            if rx < accel_zone_x:
                active_pedal = "ACCEL"
                raw_accel = map_value(ry, rest_y, accel_press_y, 0, 255)
            elif rx < brake_zone_x:
                active_pedal = "BRAKE"
                raw_brake = map_value(ry, rest_y, brake_press_y, 0, 255)

        raw_clutch = 0
        if yellow_blob:
            raw_clutch = map_value(yellow_blob[1], clutch_rest_y, clutch_press_y, 0, 255)

        smooth_accel  = SMOOTHING * smooth_accel  + (1 - SMOOTHING) * raw_accel
        smooth_brake  = SMOOTHING * smooth_brake  + (1 - SMOOTHING) * raw_brake
        smooth_clutch = SMOOTHING * smooth_clutch + (1 - SMOOTHING) * raw_clutch

        out_accel  = int(smooth_accel)
        out_brake  = int(smooth_brake)
        out_clutch = int(smooth_clutch)

        # ── Read steering + gear buttons
        steering.poll()
        steering_value = steering.get_steering_axis()
        downshift      = steering.get_downshift()
        upshift        = steering.get_upshift()

        # ── Send merged output to virtual gamepad
        clutch_axis = map_value(out_clutch, 0, 255, -32768, 32767)
        gamepad.right_trigger(value=out_accel)
        gamepad.left_trigger(value=out_brake)
        gamepad.left_joystick(x_value=0, y_value=clutch_axis)
        gamepad.right_joystick(x_value=steering_value, y_value=0)

        if downshift:
            gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
        else:
            gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)

        if upshift:
            gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        else:
            gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)

        gamepad.update()

        # ── Update state
        fps_frames += 1
        elapsed = time.time() - fps_timer
        if elapsed >= 1.0:
            state["fps"] = fps_frames / elapsed
            fps_frames   = 0
            fps_timer    = time.time()

        state["red_blob"]     = red_blob
        state["yellow_blob"]  = yellow_blob
        state["active_pedal"] = active_pedal
        state["accel"]        = out_accel
        state["brake"]        = out_brake
        state["clutch"]       = out_clutch
        state["steering"]     = steering_value
        state["downshift"]    = downshift
        state["upshift"]      = upshift

        print(f"\r  ACCEL: {out_accel:3d}/255  "
              f"BRAKE: {out_brake:3d}/255  "
              f"CLUTCH: {out_clutch:3d}/255  "
              f"STEER: {steering_value:+6d}  "
              f"DN: {'▼' if downshift else ' '}  "
              f"UP: {'▲' if upshift   else ' '}  "
              f"| FPS: {state['fps']:.1f}   ", end="", flush=True)

        if PREVIEW:
            cv2.imshow("Foot Pedal Tracker", draw_preview(frame.copy(), calib, state))

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("\n[INFO] Quitting...")
            break
        elif key == ord('r'):
            print("\n[INFO] Starting recalibration...")
            calib = run_calibration(cap)
        elif key == ord('p'):
            PREVIEW = not PREVIEW
            if not PREVIEW:
                cv2.destroyWindow("Foot Pedal Tracker")
            print(f"\n[INFO] Preview {'ON' if PREVIEW else 'OFF'}")

    # ── Cleanup
    gamepad.right_trigger(value=0)
    gamepad.left_trigger(value=0)
    gamepad.left_joystick(x_value=0, y_value=0)
    gamepad.right_joystick(x_value=0, y_value=0)
    gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
    gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
    gamepad.update()

    cap.release()
    steering.close()
    cv2.destroyAllWindows()
    print("[INFO] Stopped cleanly.")


if __name__ == "__main__":
    main()