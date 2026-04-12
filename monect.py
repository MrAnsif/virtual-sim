import pygame
pygame.init(); pygame.joystick.init()
for i in range(pygame.joystick.get_count()):
    j = pygame.joystick.Joystick(i); j.init()
    print(f"[{i}] {j.get_name()}")