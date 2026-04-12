"""
=============================================================
  STEERING INPUT MODULE
  Reads steering axis from Monect (or any virtual joystick)
  and returns a value ready to send to vgamepad right stick X.

  REQUIREMENTS:
      pip install pygame

  USAGE:
      from steering_input import SteeringInput
=============================================================
"""

import pygame

# Partial name to match against — case-insensitive substring match.
# "xbox 360" will match Monect's "Xbox 360 Controller".
# Change this if Monect shows a different name on your system.
MONECT_NAME_HINT = "xbox 360"

# Axis index for steering (A0 confirmed from diagnosis)
STEERING_AXIS = 0


class SteeringInput:

    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self._joystick = None
        self._joystick_index = None
        self._connect()

    def _connect(self):
        count = pygame.joystick.get_count()
        if count == 0:
            print("[STEERING] No joystick found. Steering will default to center.")
            return

        # Find the FIRST joystick whose name matches the hint
        # that is NOT the vgamepad we created (vgamepad registers after us)
        for i in range(count):
            j = pygame.joystick.Joystick(i)
            j.init()
            if MONECT_NAME_HINT.lower() in j.get_name().lower():
                self._joystick = j
                self._joystick_index = i
                print(f"[STEERING] Connected: [{i}] {j.get_name()}")
                return

        print(f"[STEERING] No joystick matching '{MONECT_NAME_HINT}' found.")
        print(f"[STEERING] Available joysticks:")
        for i in range(count):
            j = pygame.joystick.Joystick(i)
            print(f"           [{i}] {j.get_name()}")
        print("[STEERING] Update MONECT_NAME_HINT in steering_input.py to match.")

    def refresh(self):
        """
        Call this if vgamepad was created after SteeringInput and the wrong
        controller is being read. Re-scans and picks the correct joystick
        by name, skipping any newly added virtual controllers if possible.
        """
        pygame.joystick.quit()
        pygame.joystick.init()
        self._joystick = None
        self._connect()

    def get_steering_axis(self) -> int:
        """
        Returns steering value as int in range -32768 to 32767.
        Returns 0 (center) if no joystick is connected.
        """
        if not self._joystick:
            return 0
        try:
            pygame.event.pump()
            raw = self._joystick.get_axis(STEERING_AXIS)   # -1.0 to +1.0
            value = int(raw * 32767)
            return max(-32768, min(32767, value))
        except Exception:
            return 0

    def close(self):
        pygame.quit()

    @staticmethod
    def list_joysticks():
        """Run once standalone to find the correct MONECT_NAME_HINT."""
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