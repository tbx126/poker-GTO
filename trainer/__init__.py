"""GTO Trainer module for interactive poker training.

Provides:
- Scenario generation for specific situations
- Real-time strategy feedback
- EV loss calculation
- Spaced repetition for leak correction
"""

from trainer.scenario import Scenario, ScenarioGenerator
from trainer.feedback import Feedback, FeedbackEngine
from trainer.session import TrainingSession, SessionManager
from trainer.leak_detector import LeakDetector, LeakReport

__all__ = [
    "Scenario",
    "ScenarioGenerator",
    "Feedback",
    "FeedbackEngine",
    "TrainingSession",
    "SessionManager",
    "LeakDetector",
    "LeakReport",
]
