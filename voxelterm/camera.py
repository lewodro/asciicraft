"""First-person fly camera."""

from __future__ import annotations

import math


class Camera:
    __slots__ = ("x", "y", "z", "yaw", "pitch", "fov", "speed")

    def __init__(self, x: float, y: float, z: float,
                 yaw: float = 0.0, pitch: float = 0.0,
                 fov_degrees: float = 76.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        self.yaw = float(yaw)
        self.pitch = float(pitch)
        self.fov = math.radians(fov_degrees)
        # Walking the full 1024-wide world takes about five minutes.
        self.speed = 3.4

    def basis(self):
        """Return (forward, right, up), an orthonormal camera basis."""
        cy = math.cos(self.yaw)
        sy = math.sin(self.yaw)
        cp = math.cos(self.pitch)
        sp = math.sin(self.pitch)
        forward = (sy * cp, sp, cy * cp)
        right = (cy, 0.0, -sy)
        up = (-sy * sp, cp, -cy * sp)
        return forward, right, up

    def move(self, dt: float, forward: float, strafe: float,
             vertical: float, world, sprint: bool = False) -> None:
        mag = math.hypot(forward, strafe)
        if mag > 1.0:
            forward /= mag
            strafe /= mag
        speed = self.speed * (1.8 if sprint else 1.0)
        cy = math.cos(self.yaw)
        sy = math.sin(self.yaw)
        # Horizontal flight keeps the camera level; Space/C handle altitude.
        dx = (sy * forward + cy * strafe) * speed * dt
        dz = (cy * forward - sy * strafe) * speed * dt
        self.x += dx
        self.z += dz
        self.y += vertical * speed * dt
        self.x = max(1.2, min(world.width - 1.2, self.x))
        self.z = max(1.2, min(world.depth - 1.2, self.z))
        self.y = max(1.2, min(world.height - 1.2, self.y))

    def look(self, dyaw: float, dpitch: float) -> None:
        self.yaw = (self.yaw + dyaw) % (2.0 * math.pi)
        limit = math.radians(88.0)
        self.pitch = max(-limit, min(limit, self.pitch + dpitch))

    def teleport(self, x: float, y: float, z: float, yaw: float, pitch: float) -> None:
        self.x, self.y, self.z = float(x), float(y), float(z)
        self.yaw, self.pitch = float(yaw), float(pitch)
