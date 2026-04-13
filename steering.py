"""
=============================================================
  STEERING INPUT MODULE
  Reads from Monect vJoy:
    Axis 1       → Steering (right stick X)
    Button 0     → Downshift (gamepad button)
    Button 1     → Upshift   (gamepad button)

  REQUIREMENTS:
      pip install pygame

  USAGE:
      from steering_input import SteeringInput
=============================================================
"""

import pygame

MONECT_NAME_HINT = "vjoy"       # case-insensitive substring match

STEERING_AXIS    = 1            # confirmed from vjoy_inspector
DOWNSHIFT_BUTTON = 0            # confirmed from vjoy_inspector
UPSHIFT_BUTTON   = 1            # confirmed from vjoy_inspector


class SteeringInput:

    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self._joystick  = None
        self._connect()

    def _connect(self):
        count = pygame.joystick.get_count()
        if count == 0:
            print("[STEERING] No joystick found. Steering/gear input will be inactive.")
            return
        for i in range(count):
            j = pygame.joystick.Joystick(i)
            j.init()
            if MONECT_NAME_HINT.lower() in j.get_name().lower():
                self._joystick = j
                print(f"[STEERING] Connected: [{i}] {j.get_name()}")
                return
        print(f"[STEERING] No joystick matching '{MONECT_NAME_HINT}' found.")
        print("[STEERING] Available joysticks:")
        for i in range(count):
            print(f"           [{i}] {pygame.joystick.Joystick(i).get_name()}")
        print("[STEERING] Update MONECT_NAME_HINT in steering_input.py to match.")

    def refresh(self):
        """Re-scan joysticks. Call if controller list changed at runtime."""
        pygame.joystick.quit()
        pygame.joystick.init()
        self._joystick = None
        self._connect()

    def poll(self):
        """
        Call ONCE per frame — pumps pygame events so all getters
        below reflect the latest state.
        """
        if self._joystick:
            pygame.event.pump()

    def get_steering_axis(self) -> int:
        """Steering as int -32768 to 32767. 0 = center."""
        if not self._joystick:
            return 0
        try:
            raw = self._joystick.get_axis(STEERING_AXIS)
            return max(-32768, min(32767, int(raw * 32767)))
        except Exception:
            return 0

    def get_downshift(self) -> bool:
        """True while downshift button is held."""
        if not self._joystick:
            return False
        try:
            return bool(self._joystick.get_button(DOWNSHIFT_BUTTON))
        except Exception:
            return False

    def get_upshift(self) -> bool:
        """True while upshift button is held."""
        if not self._joystick:
            return False
        try:
            return bool(self._joystick.get_button(UPSHIFT_BUTTON))
        except Exception:
            return False

    def close(self):
        pygame.quit()
        print("[STEERING] Stopped.")

    @staticmethod
    def list_joysticks():
        pygame.init()
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        print(f"Found {count} joystick(s):")
        for i in range(count):
            j = pygame.joystick.Joystick(i)
            j.init()
            print(f"  [{i}] {j.get_name()}")
        pygame.quit()


if __name__ == "__main__":
    SteeringInput.list_joysticks()