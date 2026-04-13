"""
=============================================================
  vJoy / Joystick Input Inspector
  Prints all axes, buttons, and hats in real time.
  Use this to find which axis/button Monect maps to.

  REQUIREMENTS:
      pip install pygame
=============================================================
"""

import pygame
import time
import os

JOYSTICK_INDEX = 0   # Change if vJoy is not the first joystick


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def main():
    pygame.init()
    pygame.joystick.init()

    count = pygame.joystick.get_count()
    print(f"\nDetected {count} joystick(s):\n")
    for i in range(count):
        j = pygame.joystick.Joystick(i)
        j.init()
        print(f"  [{i}] {j.get_name()}")

    if count == 0:
        print("\n[ERROR] No joystick found. Make sure Monect is connected and vJoy is active.")
        return

    print(f"\nMonitoring joystick [{JOYSTICK_INDEX}]. Change JOYSTICK_INDEX if wrong.")
    print("Move each control on your phone and watch what changes.\n")
    input("Press ENTER to start monitoring...\n")

    joy = pygame.joystick.Joystick(JOYSTICK_INDEX)
    joy.init()

    num_axes    = joy.get_numaxes()
    num_buttons = joy.get_numbuttons()
    num_hats    = joy.get_numhats()

    print(f"  Axes: {num_axes}  |  Buttons: {num_buttons}  |  Hats: {num_hats}\n")

    prev_axes    = [0.0] * num_axes
    prev_buttons = [0]   * num_buttons
    prev_hats    = [(0,0)] * num_hats

    try:
        while True:
            pygame.event.pump()

            axes    = [round(joy.get_axis(i), 3)   for i in range(num_axes)]
            buttons = [joy.get_button(i)            for i in range(num_buttons)]
            hats    = [joy.get_hat(i)               for i in range(num_hats)]

            # Only reprint if something changed
            if axes != prev_axes or buttons != prev_buttons or hats != prev_hats:
                clear()
                print(f"  Joystick : {joy.get_name()}")
                print(f"  Axes: {num_axes}  |  Buttons: {num_buttons}  |  Hats: {num_hats}")
                print("─" * 50)

                print("\n  AXES  (-1.0 = min, 0.0 = center, +1.0 = max)\n")
                for i, val in enumerate(axes):
                    bar_len  = 20
                    filled   = int((val + 1.0) / 2.0 * bar_len)
                    bar      = "█" * filled + "░" * (bar_len - filled)
                    changed  = " ◄ MOVING" if val != prev_axes[i] else ""
                    print(f"    Axis {i:2d}  [{bar}]  {val:+.3f}{changed}")

                print("\n  BUTTONS\n")
                for i, val in enumerate(buttons):
                    state   = "■ PRESSED " if val else "□ released"
                    changed = " ◄" if val != prev_buttons[i] else ""
                    print(f"    Button {i:2d}  {state}{changed}")

                if num_hats > 0:
                    print("\n  HATS\n")
                    for i, val in enumerate(hats):
                        changed = " ◄" if val != prev_hats[i] else ""
                        print(f"    Hat {i:2d}  {val}{changed}")

                print("\n─" * 50)
                print("  Ctrl+C to quit")

                prev_axes    = axes
                prev_buttons = buttons
                prev_hats    = hats

            time.sleep(0.03)

    except KeyboardInterrupt:
        print("\n\n[INFO] Stopped.")
        pygame.quit()


if __name__ == "__main__":
    main()