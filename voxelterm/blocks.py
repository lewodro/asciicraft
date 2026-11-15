"""Voxel block ids, palettes and face-lighting constants."""

from __future__ import annotations

# Block ids.  Keep AIR == 0 so a zero-filled world is empty.
AIR = 0
GRASS = 1
DIRT = 2
STONE = 3
WATER = 4
WOOD = 5
LEAVES = 6
SAND = 7
SNOW = 8

BLOCK_NAMES = {
    AIR: "air",
    GRASS: "grass",
    DIRT: "dirt",
    STONE: "stone",
    WATER: "water",
    WOOD: "wood",
    LEAVES: "leaves",
    SAND: "sand",
    SNOW: "snow",
}

# Lighting is deliberately stylised, not physically correct.  The strong
# separation between the six face directions is what makes cubes read as cubes.
# Side and underside values stay well below the sunlit top, but the palette is
# lifted enough that shaded faces keep their material colour.
FACE_LIGHT = {
    (0, 1, 0): 1.00,
    (0, -1, 0): 0.44,
    (1, 0, 0): 0.70,
    (-1, 0, 0): 0.65,
    (0, 0, 1): 0.88,
    (0, 0, -1): 0.81,
}

# Blocks that fully occlude a neighbouring face.
OCCLUDERS = frozenset((GRASS, DIRT, STONE, WOOD, SAND, SNOW))
