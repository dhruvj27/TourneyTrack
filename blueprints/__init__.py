"""
Blueprints package for TourneyTrack application
Contains modular route blueprints for different features
"""

from .auth import auth_bp
from .smc import smc_bp
from .team import team_bp
from .public import public_bp

__all__ = ['auth_bp', 'smc_bp', 'team_bp', 'public_bp']