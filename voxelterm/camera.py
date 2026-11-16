"""First-person fly camera."""

from __future__ import annotations

import math


class Camera:
    __slots__ = ("x", "y", "z", "yaw", "pitch", "fov", "speed",
                 "vx", "vy", "vz")

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
        self.vx = self.vy = self.vz = 0.0

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
        mag = math.sqrt(forward * forward + strafe * strafe + vertical * vertical)
        if mag > 1.0:
            forward /= mag
            strafe /= mag
            vertical /= mag
        speed = self.speed * (1.8 if sprint else 1.0)
        cy = math.cos(self.yaw)
        sy = math.sin(self.yaw)
        # Horizontal flight keeps the camera level; Space/C handle altitude.
        target_x = (sy * forward + cy * strafe) * speed
        target_z = (cy * forward - sy * strafe) * speed
        target_y = vertical * speed

        # Exponential approach gives short acceleration and deceleration ramps
        # without adding a visible lag. Sprint also stiffens the response.
        response = 1.0 - math.exp(-(16.0 if sprint else 12.0) * dt)
        self.vx += (target_x - self.vx) * response
        self.vy += (target_y - self.vy) * response
        self.vz += (target_z - self.vz) * response

        self.x += self.vx * dt
        self.z += self.vz * dt
        self.y += self.vy * dt

        # Stop cleanly at the finite world edge instead of buzzing against it.
        if self.x < 1.2:
            self.x, self.vx = 1.2, 0.0
        elif self.x > world.width - 1.2:
            self.x, self.vx = world.width - 1.2, 0.0
        if self.z < 1.2:
            self.z, self.vz = 1.2, 0.0
        elif self.z > world.depth - 1.2:
            self.z, self.vz = world.depth - 1.2, 0.0
        if self.y < 1.2:
            self.y, self.vy = 1.2, 0.0
        elif self.y > world.height - 1.2:
            self.y, self.vy = world.height - 1.2, 0.0

    def look(self, dyaw: float, dpitch: float) -> None:
        self.yaw = (self.yaw + dyaw) % (2.0 * math.pi)
        limit = math.radians(88.0)
        self.pitch = max(-limit, min(limit, self.pitch + dpitch))

    def teleport(self, x: float, y: float, z: float, yaw: float, pitch: float) -> None:
        self.x, self.y, self.z = float(x), float(y), float(z)
        self.yaw, self.pitch = float(yaw), float(pitch)
        self.vx = self.vy = self.vz = 0.0
