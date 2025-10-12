"""
Blueprints package for TourneyTrack application
Contains modular route blueprints for different features
"""

from .auth import auth_bp

__all__ = ['auth_bp']