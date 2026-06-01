"""
=============================================================
  FOOT PEDAL TRACKER  (optimized)
  Maps webcam foot detection → Virtual Xbox controller
  Red marker   = Right foot (Accelerator / Brake)
  Yellow marker = Left foot (Clutch)
=============================================================
REQUIREMENTS:
    pip install opencv-python numpy vgamepad pygame
ALSO INSTALL:
    ViGEmBus — https://github.com/nefarius/ViGEmBus/releases
CONTROLS:
    R — Recalibrate  |  P — Toggle preview  |  Q — Quit
=============================================================
"""

import cv2
import numpy as np
import vgamepad as vg
import json, os, time
from steering import SteeringInput

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
PREVIEW         = False
CAMERA_INDEX    = 0
TARGET_FPS      = 24
CALIB_FILE      = "pedal_calib.json"

SMOOTHING        = 0.55
MIN_BLOB_AREA    = 300
CLUTCH_THRESHOLD = 80           # 0-255: above = clutch A-button pressed
CLUTCH_HOLD_FRAMES = 6         # frames to hold last clutch value if blob lost

# Detection runs on a downscaled frame to save CPU
DETECT_W, DETECT_H = 480, 270  # half of 960x540; adjust if camera differs
SCALE_X = SCALE_Y = 1.0        # filled in main() after cap is opened

PRINT_EVERY_N = 10              # throttle console output

# ─────────────────────────────────────────────
#  HSV COLOR RANGES  (pre-built as contiguous arrays)
# ─────────────────────────────────────────────
RED_LOWER_1 = np.array([145, 120, 120], dtype=np.uint8)
RED_UPPER_1 = np.array([165, 255, 255], dtype=np.uint8)
RED_LOWER_2 = np.array([0,   120, 120], dtype=np.uint8)   # wraps hue 0-10
RED_UPPER_2 = np.array([10,  255, 255], dtype=np.uint8)

YELLOW_LOWER = np.array([18, 100, 100], dtype=np.uint8)
YELLOW_UPPER = np.array([38, 255, 255], dtype=np.uint8)

# Morphology kernels (small = cheaper)
_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

# ─────────────────────────────────────────────
#  CALIBRATION DEFAULT
# ─────────────────────────────────────────────
DEFAULT_CALIB = {
    "floor_y": 400, "accel_zone_x": 450, "brake_zone_x": 250,
    "accel_press_y": 350, "brake_press_y": 350,
    "clutch_rest_y": 300, "clutch_press_y": 400,
    "frame_width": 640,   "frame_height": 480
}

# ─────────────────────────────────────────────
#  UTILITY
# ─────────────────────────────────────────────
def map_value(val, in_min, in_max, out_min, out_max):
    if in_max == in_min:
        return out_min
    r = max(0.0, min(1.0, (val - in_min) / (in_max - in_min)))
    return int(out_min + r * (out_max - out_min))


def get_blob_centroid(mask):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < MIN_BLOB_AREA:
        return None
    M = cv2.moments(largest)
    if M["m00"] == 0:
        return None
    return int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]), largest


def detect_color(hsv_roi, color):
    """Returns (cx, cy, contour) in ROI coords, or None."""
    if color == "red":
        mask = cv2.bitwise_or(
            cv2.inRange(hsv_roi, RED_LOWER_1, RED_UPPER_1),
            cv2.inRange(hsv_roi, RED_LOWER_2, RED_UPPER_2)
        )
    else:
        mask = cv2.inRange(hsv_roi, YELLOW_LOWER, YELLOW_UPPER)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  _KERNEL)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _KERNEL)
    return get_blob_centroid(mask)


# ─────────────────────────────────────────────
#  CALIBRATION  (unchanged logic, same UX)
# ─────────────────────────────────────────────
def load_calibration():
    if os.path.exists(CALIB_FILE):
        with open(CALIB_FILE) as f:
            print("[INFO] Calibration loaded.")
            return json.load(f)
    print("[INFO] No calibration file — using defaults.")
    return DEFAULT_CALIB.copy()


def save_calibration(calib):
    with open(CALIB_FILE, "w") as f:
        json.dump(calib, f, indent=2)
    print("[INFO] Calibration saved.")


def run_calibration(cap):
    print("\n[CALIBRATION STARTED]")
    calib = {}
    ret, frame = cap.read()
    h, w = frame.shape[:2]
    calib["frame_width"], calib["frame_height"] = w, h

    steps = [
        ("floor_y + zones", "Step 1/7: Both feet FLAT — resting.\n         SPACE to capture."),
        ("accel_zone_x",    "Step 2/7: Right foot FAR RIGHT (accel).\n         SPACE to capture."),
        ("brake_zone_x",    "Step 3/7: Right foot CENTERED (brake).\n         SPACE to capture."),
        ("accel_press_y",   "Step 4/7: Right foot FAR RIGHT, FULLY pressed.\n         SPACE to capture."),
        ("brake_press_y",   "Step 5/7: Right foot CENTERED, FULLY pressed.\n         SPACE to capture."),
        ("clutch_rest_y",   "Step 6/7: Left foot FLAT, clutch released.\n         SPACE to capture."),
        ("clutch_press_y",  "Step 7/7: Left foot FULLY pressed (clutch).\n         SPACE to capture."),
    ]
    captured = {}
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    for key, instruction in steps:
        print(f"\n{instruction}")
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            # enhance for detection
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            l = clahe.apply(l)
            enhanced = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
            hsv = cv2.cvtColor(enhanced, cv2.COLOR_BGR2HSV)
            red_blob    = detect_color(hsv, "red")
            yellow_blob = detect_color(hsv, "yellow")

            display = frame.copy()
            if red_blob:
                cx, cy, cnt = red_blob
                cv2.drawContours(display, [cnt], -1, (0, 0, 255), 2)
                cv2.circle(display, (cx, cy), 6, (0, 0, 255), -1)
                cv2.putText(display, f"RED ({cx},{cy})", (cx+10, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)
            if yellow_blob:
                cx, cy, cnt = yellow_blob
                cv2.drawContours(display, [cnt], -1, (0,255,255), 2)
                cv2.circle(display, (cx, cy), 6, (0,255,255), -1)
                cv2.putText(display, f"YLW ({cx},{cy})", (cx+10, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1)
            for i, line in enumerate(instruction.split("\n")):
                cv2.putText(display, line.strip(), (10, 30+i*25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
            cv2.putText(display, "SPACE=Capture  Q=Skip",
                        (10, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
            cv2.imshow("Calibration", display)
            k = cv2.waitKey(1) & 0xFF

            if k == ord(' '):
                if red_blob:    captured["red_cx"],    captured["red_cy"]    = red_blob[0],    red_blob[1]
                if yellow_blob: captured["yellow_cx"], captured["yellow_cy"] = yellow_blob[0], yellow_blob[1]

                if   key == "floor_y + zones":
                    ys = []
                    if red_blob:    ys.append(red_blob[1])
                    if yellow_blob: ys.append(yellow_blob[1])
                    calib["floor_y"] = max(ys)+20 if ys else h-20
                elif key == "accel_zone_x":   calib["accel_zone_x"]  = captured.get("red_cx",    w*0.7)
                elif key == "brake_zone_x":   calib["brake_zone_x"]  = captured.get("red_cx",    w*0.4)
                elif key == "accel_press_y":  calib["accel_press_y"] = captured.get("red_cy",    h*0.8)
                elif key == "brake_press_y":  calib["brake_press_y"] = captured.get("red_cy",    h*0.8)
                elif key == "clutch_rest_y":  calib["clutch_rest_y"] = captured.get("yellow_cy", h*0.5)
                elif key == "clutch_press_y": calib["clutch_press_y"]= captured.get("yellow_cy", h*0.85)
                print(f"  {key} captured.")
                break
            elif k == ord('q'):
                print("  Step skipped.")
                break

    cv2.destroyWindow("Calibration")
    save_calibration(calib)
    return calib


# ─────────────────────────────────────────────
#  PREVIEW OVERLAY
# ─────────────────────────────────────────────
def draw_preview(frame, calib, state):
    h, w = frame.shape[:2]
    ax       = int(calib.get("accel_zone_x", w*0.35))
    bx       = int(calib.get("brake_zone_x", w*0.70))
    floor_y  = int(calib.get("floor_y",      h-20))

    overlay = frame.copy()
    cv2.rectangle(overlay, (0,  0), (ax, floor_y), (0, 80, 0),   -1)
    cv2.rectangle(overlay, (ax, 0), (bx, floor_y), (0, 0, 80),   -1)
    cv2.rectangle(overlay, (bx, 0), (w,  floor_y), (50,50,50),   -1)
    cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)

    cv2.line(frame, (ax,0),(ax,floor_y),(0,255,0),2)
    cv2.line(frame, (bx,0),(bx,floor_y),(0,80,255),2)
    cv2.line(frame, (0,floor_y),(w,floor_y),(255,255,0),2)
    cv2.putText(frame,"ACCEL ZONE",(5,20),        cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,255,0),1)
    cv2.putText(frame,"BRAKE ZONE",(ax+5,20),     cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,100,255),1)
    cv2.putText(frame,"CLUTCH AREA",(bx+5,20),    cv2.FONT_HERSHEY_SIMPLEX,0.5,(150,150,150),1)
    cv2.putText(frame,"FLOOR",(5,floor_y-5),      cv2.FONT_HERSHEY_SIMPLEX,0.4,(255,255,0),1)

    if state["red_blob"]:
        cx, cy, cnt = state["red_blob"]
        cv2.drawContours(frame,[cnt],-1,(0,0,255),2)
        cv2.circle(frame,(cx,cy),8,(0,0,255),-1)
        cv2.putText(frame,f"R.FOOT|{state['active_pedal']}",(cx+10,cy-10),
                    cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,0,255),2)
    if state["yellow_blob"]:
        cx, cy, cnt = state["yellow_blob"]
        cv2.drawContours(frame,[cnt],-1,(0,255,255),2)
        cv2.circle(frame,(cx,cy),8,(0,255,255),-1)
        cv2.putText(frame,"L.FOOT|CLUTCH",(cx+10,cy-10),
                    cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,255,255),2)

    # HUD bars
    hx, hy = 10, h-240
    bw, bh, gap = 150, 18, 26

    def bar(label, v255, color, yo):
        pct = v255/255.0
        fx  = int(bw*pct)
        cv2.rectangle(frame,(hx,hy+yo),(hx+bw,hy+yo+bh),(50,50,50),-1)
        if fx: cv2.rectangle(frame,(hx,hy+yo),(hx+fx,hy+yo+bh),color,-1)
        cv2.rectangle(frame,(hx,hy+yo),(hx+bw,hy+yo+bh),(180,180,180),1)
        cv2.putText(frame,f"{label}:{int(pct*100)}%",(hx+bw+6,hy+yo+13),
                    cv2.FONT_HERSHEY_SIMPLEX,0.45,color,1)

    bar("ACCEL", state["accel"],  (0,220,0),   0)
    bar("BRAKE", state["brake"],  (0,80,255),  gap)
    bar("CLUTCH",state["clutch"], (0,220,220), gap*2)

    # Steering
    sy   = gap*3
    sv   = state.get("steering",0)
    cx_s = hx+bw//2
    pct  = sv/32767.0
    fl   = int((bw//2)*abs(pct))
    cv2.rectangle(frame,(hx,hy+sy),(hx+bw,hy+sy+bh),(50,50,50),-1)
    if pct<0: cv2.rectangle(frame,(cx_s-fl,hy+sy),(cx_s,hy+sy+bh),(0,165,255),-1)
    else:     cv2.rectangle(frame,(cx_s,hy+sy),(cx_s+fl,hy+sy+bh),(255,200,0),-1)
    cv2.line(frame,(cx_s,hy+sy),(cx_s,hy+sy+bh),(255,255,255),1)
    cv2.rectangle(frame,(hx,hy+sy),(hx+bw,hy+sy+bh),(180,180,180),1)
    cv2.putText(frame,f"STEER:{'L' if pct<0 else 'R'} {int(abs(pct)*100)}%",
                (hx+bw+6,hy+sy+13),cv2.FONT_HERSHEY_SIMPLEX,0.45,(200,200,100),1)

    # Buttons row 1: shifts
    by1 = gap*4
    dc = (0,200,255) if state.get("downshift") else (60,60,60)
    uc = (0,255,100) if state.get("upshift")   else (60,60,60)
    cv2.rectangle(frame,(hx,hy+by1),(hx+68,hy+by1+bh),dc,-1)
    cv2.rectangle(frame,(hx+76,hy+by1),(hx+bw,hy+by1+bh),uc,-1)
    cv2.putText(frame,"UP SHIFT",(hx+4,hy+by1+13),  cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,0,0),1)
    cv2.putText(frame,"DN SHIFT",(hx+80,hy+by1+13), cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,0,0),1)

    # Buttons row 2: handbrake + horn
    by2 = gap*5
    hbc  = (0,60,255)  if state.get("handbrake") else (60,60,60)
    hrc  = (255,200,0) if state.get("horn")       else (60,60,60)
    cv2.rectangle(frame,(hx,hy+by2),(hx+68,hy+by2+bh),hbc,-1)
    cv2.rectangle(frame,(hx+76,hy+by2),(hx+bw,hy+by2+bh),hrc,-1)
    cv2.putText(frame,"H.BRAKE",(hx+4,hy+by2+13),  cv2.FONT_HERSHEY_SIMPLEX,0.4,(255,255,255),1)
    cv2.putText(frame,"HORN",   (hx+80,hy+by2+13), cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,0,0),1)

    cv2.putText(frame,f"FPS:{state['fps']:.1f}",(w-80,20),
                cv2.FONT_HERSHEY_SIMPLEX,0.5,(200,200,200),1)
    cv2.putText(frame,"R=Recalib  P=Preview  Q=Quit",
                (10,h-10),cv2.FONT_HERSHEY_SIMPLEX,0.4,(150,150,150),1)
    return frame


# ─────────────────────────────────────────────
#  GAMEPAD HELPER  — only call update() when state changed
# ─────────────────────────────────────────────
class GamepadManager:
    """Wraps vgamepad and only flushes update() when output changed."""

    BTN_LB = vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER
    BTN_RB = vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER
    BTN_RS = vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB

    # RS joystick Y axis values
    RS_UP   =  32767   # Clutch   → RS UP
    RS_DOWN = -32767   # Handbrake → RS DOWN
    RS_IDLE =  0

    def __init__(self):
        self.gp = vg.VX360Gamepad()
        self._rt = self._lt = self._steer = 0
        self._rs_y = 0          # tracks current RS Y value
        self._clutch_pressed   = False
        self._handbrake_pressed = False
        self._btns = {self.BTN_LB: False, self.BTN_RB: False, self.BTN_RS: False}
        self._dirty = False

    def _set_btn(self, btn, pressed):
        if self._btns[btn] != pressed:
            if pressed: self.gp.press_button(button=btn)
            else:       self.gp.release_button(button=btn)
            self._btns[btn] = pressed
            self._dirty = True

    def _update_rs_y(self):
        """RS Y: clutch (up) takes priority over handbrake (down)."""
        if self._clutch_pressed:
            target = self.RS_UP
        elif self._handbrake_pressed:
            target = self.RS_DOWN
        else:
            target = self.RS_IDLE
        if target != self._rs_y:
            self.gp.right_joystick(x_value=self._steer, y_value=target)
            self._rs_y = target
            self._dirty = True

    def _set_joystick_rs_up(self, pressed):
        if self._clutch_pressed != pressed:
            self._clutch_pressed = pressed
            self._update_rs_y()

    def _set_joystick_rs_down(self, pressed):
        if self._handbrake_pressed != pressed:
            self._handbrake_pressed = pressed
            self._update_rs_y()

    def set_triggers(self, rt, lt):
        if rt != self._rt:
            self.gp.right_trigger(value=rt); self._rt = rt; self._dirty = True
        if lt != self._lt:
            self.gp.left_trigger(value=lt);  self._lt = lt; self._dirty = True

    def set_steering(self, x):
        if x != self._steer:
            self._steer = x
            self.gp.left_joystick(x_value=x, y_value=0)   # FH4 steering = Left Stick X
            self._dirty = True

    def set_clutch(self, val):   self._set_joystick_rs_up(val > CLUTCH_THRESHOLD)
    def set_downshift(self, v):  self._set_btn(self.BTN_RB, v)
    def set_upshift(self, v):    self._set_btn(self.BTN_LB, v)
    def set_handbrake(self, v):  self._set_joystick_rs_down(v)
    def set_horn(self, v):       self._set_btn(self.BTN_RS, v)

    def flush(self):
        if self._dirty:
            self.gp.update()
            self._dirty = False

    def reset(self):
        self.gp.right_trigger(value=0)
        self.gp.left_trigger(value=0)
        self.gp.right_joystick(x_value=0, y_value=0)
        for btn in self._btns:
            self.gp.release_button(button=btn)
        self.gp.update()


# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────
def main():
    global PREVIEW, SCALE_X, SCALE_Y

    print("=" * 55)
    print("  FOOT PEDAL TRACKER — Starting (optimized)")
    print("=" * 55)

    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS,          TARGET_FPS)
    # disable auto-exposure/WB if driver supports it (reduces CPU latency)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("[ERROR] Cannot open camera. Check CAMERA_INDEX.")
        return

    ret, probe = cap.read()
    CAM_H, CAM_W = probe.shape[:2]
    SCALE_X = DETECT_W / CAM_W
    SCALE_Y = DETECT_H / CAM_H
    print(f"[INFO] Camera: {CAM_W}x{CAM_H} → detect at {DETECT_W}x{DETECT_H}")

    calib = load_calibration()
    if not os.path.exists(CALIB_FILE):
        calib = run_calibration(cap)

    steering_in = SteeringInput()

    try:
        gpm = GamepadManager()
        print("[INFO] Virtual Xbox controller created.")
    except Exception as e:
        print(f"[ERROR] Could not create virtual gamepad: {e}")
        cap.release(); steering_in.close(); return

    # Pre-allocate reusable small frame
    small = np.empty((DETECT_H, DETECT_W, 3), dtype=np.uint8)

    smooth_accel = smooth_brake = smooth_clutch = 0.0
    ONE_MINUS_S  = 1.0 - SMOOTHING
    clutch_lost_frames = 0          # counts consecutive frames with no yellow blob
    last_raw_clutch    = 0          # last known clutch value before blob was lost

    state = {
        "red_blob": None, "yellow_blob": None, "active_pedal": "NONE",
        "accel": 0, "brake": 0, "clutch": 0, "steering": 0,
        "downshift": False, "upshift": False,
        "handbrake": False, "horn": False, "fps": 0.0,
    }

    clahe      = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    fps_timer  = time.time()
    fps_frames = frame_count = 0

    # Scale calibration coords down to detection resolution once
    def scaled_calib():
        return {
            "floor_y":       calib.get("floor_y",       CAM_H-20) * SCALE_Y,
            "accel_zone_x":  calib.get("accel_zone_x",  CAM_W*0.7) * SCALE_X,
            "brake_zone_x":  calib.get("brake_zone_x",  CAM_W*0.4) * SCALE_X,
            "accel_press_y": calib.get("accel_press_y", CAM_H*0.85)* SCALE_Y,
            "brake_press_y": calib.get("brake_press_y", CAM_H*0.85)* SCALE_Y,
            "clutch_rest_y": calib.get("clutch_rest_y", CAM_H*0.55)* SCALE_Y,
            "clutch_press_y":calib.get("clutch_press_y",CAM_H*0.85)* SCALE_Y,
        }

    sc = scaled_calib()

    if PREVIEW:
        cv2.namedWindow("Foot Pedal Tracker", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Foot Pedal Tracker", 640, 480)

    print("[INFO] Running. Q=quit  R=recalibrate  P=toggle preview\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        # ── Downscale for detection only
        cv2.resize(frame, (DETECT_W, DETECT_H), dst=small, interpolation=cv2.INTER_LINEAR)

        # ── CLAHE on small copy (don't touch display frame)
        lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
        l, a, b_ch = cv2.split(lab)
        clahe.apply(l, dst=l)
        cv2.merge([l, a, b_ch], dst=lab)
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        # ── ROI: bottom 65% of small frame
        roi_top_s = int(DETECT_H * 0.35)
        roi_hsv   = cv2.cvtColor(enhanced[roi_top_s:], cv2.COLOR_BGR2HSV)

        red_res    = detect_color(roi_hsv, "red")
        yellow_res = detect_color(roi_hsv, "yellow")

        # ── Scale detections back to full-frame coords for display/logic
        red_blob = yellow_blob = None
        if red_res:
            cx, cy, cnt = red_res
            cx_f = int(cx / SCALE_X)
            cy_f = int((cy + roi_top_s) / SCALE_Y)
            cnt_f = (cnt / np.array([[[SCALE_X, SCALE_Y]]])).astype(np.int32) \
                    + np.array([[[0, int(roi_top_s / SCALE_Y)]]])
            red_blob = (cx_f, cy_f, cnt_f)
        if yellow_res:
            cx, cy, cnt = yellow_res
            cx_f = int(cx / SCALE_X)
            cy_f = int((cy + roi_top_s) / SCALE_Y)
            cnt_f = (cnt / np.array([[[SCALE_X, SCALE_Y]]])).astype(np.int32) \
                    + np.array([[[0, int(roi_top_s / SCALE_Y)]]])
            yellow_blob = (cx_f, cy_f, cnt_f)

        # ── Pedal logic (uses small-frame scaled calib coords)
        raw_accel = raw_brake = 0
        active_pedal = "NONE"

        if red_res:
            rx = red_res[0]; ry = red_res[1] + roi_top_s
            rest_y = sc["floor_y"] - 180 * SCALE_Y
            if rx < sc["accel_zone_x"]:
                active_pedal = "ACCEL"
                raw_accel = map_value(ry, rest_y, sc["accel_press_y"], 0, 255)
            elif rx < sc["brake_zone_x"]:
                active_pedal = "BRAKE"
                raw_brake = map_value(ry, rest_y, sc["brake_press_y"], 0, 255)

        if yellow_res:
            ry = yellow_res[1] + roi_top_s
            raw_clutch = map_value(ry, sc["clutch_rest_y"], sc["clutch_press_y"], 0, 255)
            last_raw_clutch    = raw_clutch
            clutch_lost_frames = 0
        else:
            clutch_lost_frames += 1
            # Hold last value for CLUTCH_HOLD_FRAMES, then release gradually
            raw_clutch = last_raw_clutch if clutch_lost_frames <= CLUTCH_HOLD_FRAMES else 0

        smooth_accel  = SMOOTHING * smooth_accel  + ONE_MINUS_S * raw_accel
        smooth_brake  = SMOOTHING * smooth_brake  + ONE_MINUS_S * raw_brake
        smooth_clutch = SMOOTHING * smooth_clutch + ONE_MINUS_S * raw_clutch

        out_accel  = int(smooth_accel)
        out_brake  = int(smooth_brake)
        out_clutch = int(smooth_clutch)

        # ── Steering + buttons
        steering_in.poll()
        steer_val = steering_in.get_steering_axis()
        downshift = steering_in.get_downshift()
        upshift   = steering_in.get_upshift()
        handbrake = steering_in.get_handbrake()
        horn      = steering_in.get_horn()

        # ── Gamepad — only flushes if anything changed
        gpm.set_triggers(out_accel, out_brake)
        gpm.set_steering(steer_val)
        gpm.set_clutch(out_clutch)
        gpm.set_downshift(downshift)
        gpm.set_upshift(upshift)
        gpm.set_handbrake(handbrake)
        gpm.set_horn(horn)
        gpm.flush()

        # ── FPS counter
        fps_frames += 1
        frame_count += 1
        elapsed = time.time() - fps_timer
        if elapsed >= 1.0:
            state["fps"] = fps_frames / elapsed
            fps_frames   = 0
            fps_timer    = time.time()

        # ── State update
        state.update({
            "red_blob": red_blob, "yellow_blob": yellow_blob,
            "active_pedal": active_pedal,
            "accel": out_accel, "brake": out_brake, "clutch": out_clutch,
            "steering": steer_val,
            "downshift": downshift, "upshift": upshift,
            "handbrake": handbrake, "horn": horn,
        })

        # ── Console print (throttled)
        if frame_count % PRINT_EVERY_N == 0:
            print(f"\r  ACCEL:{out_accel:3d}  BRAKE:{out_brake:3d}  "
                  f"CLUTCH:{out_clutch:3d}  STEER:{steer_val:+6d}  "
                  f"DN:{'▼' if downshift else ' '}  UP:{'▲' if upshift else ' '}  "
                  f"HB:{'■' if handbrake else ' '}  HORN:{'♪' if horn else ' '}  "
                  f"FPS:{state['fps']:.1f}   ", end="", flush=True)

        # ── Preview
        if PREVIEW:
            cv2.imshow("Foot Pedal Tracker", draw_preview(frame, calib, state))

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("\n[INFO] Quitting...")
            break
        elif key == ord('r'):
            print("\n[INFO] Recalibrating...")
            calib = run_calibration(cap)
            sc    = scaled_calib()          # recompute scaled coords
        elif key == ord('p'):
            PREVIEW = not PREVIEW
            if not PREVIEW:
                cv2.destroyWindow("Foot Pedal Tracker")
            else:
                cv2.namedWindow("Foot Pedal Tracker", cv2.WINDOW_NORMAL)
                cv2.resizeWindow("Foot Pedal Tracker", 640, 480)
            print(f"\n[INFO] Preview {'ON' if PREVIEW else 'OFF'}")

    # ── Cleanup
    gpm.reset()
    cap.release()
    steering_in.close()
    cv2.destroyAllWindows()
    print("[INFO] Stopped cleanly.")


if __name__ == "__main__":
    main()