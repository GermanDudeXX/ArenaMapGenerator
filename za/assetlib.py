"""Laden und Zerschneiden der Pixel-Art-Assets."""
import os

import pygame

from .settings import ASSETS

_images = {}


def load(*parts):
    """Laedt ein Bild aus assets/ und cached es."""
    path = os.path.join(ASSETS, *parts)
    surf = _images.get(path)
    if surf is None:
        surf = pygame.image.load(path).convert_alpha()
        _images[path] = surf
    return surf


def strip(surf, fw=None, fh=None):
    """Zerschneidet einen horizontalen Spritestreifen in Einzelframes."""
    fh = fh or surf.get_height()
    fw = fw or fh
    n = max(1, surf.get_width() // fw)
    return [surf.subsurface((i * fw, 0, fw, fh)).copy() for i in range(n)]
