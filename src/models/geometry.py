"""Core geometry primitives used throughout the engine."""

from __future__ import annotations
from pydantic import BaseModel


class Point2D(BaseModel):
    x: float
    y: float


class Line2D(BaseModel):
    start: Point2D
    end: Point2D
