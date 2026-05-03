"""Training session management.

Manages training sessions with:
- Progress tracking
- Spaced repetition scheduling
- Performance analytics
- Session history
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from trainer.scenario import Scenario, ScenarioGenerator, SituationType
from trainer.feedback import Feedback, FeedbackEngine, FeedbackType


@dataclass
class Attempt:
    """A single attempt at a scenario."""
    scenario_id: str
    player_action: str
    feedback: Feedback
    timestamp: datetime = field(default_factory=datetime.now)
    time_taken_ms: int = 0


@dataclass
class ScenarioProgress:
    """Progress on a specific scenario."""
    scenario_id: str
    attempts: int = 0
    correct: int = 0
    close: int = 0
    incorrect: int = 0
    avg_ev_loss: float = 0.0
    
    # Spaced repetition
    ease_factor: float = 2.5  # SM-2 algorithm
    interval_days: float = 1.0
    next_review: datetime = field(default_factory=datetime.now)
    
    # History
    last_attempt: Optional[datetime] = None
    history: list[Attempt] = field(default_factory=list)


@dataclass
class SessionStats:
    """Statistics for a training session."""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    
    # Performance
    total_scenarios: int = 0
    correct: int = 0
    close: int = 0
    incorrect: int = 0
    accuracy: float = 0.0
    avg_ev_loss: float = 0.0
    
    # By situation type
    by_situation: dict[str, dict] = field(default_factory=dict)
    
    # Time stats
    avg_time_ms: int = 0
    total_time_ms: int = 0


class TrainingSession:
    """A training session."""
    
    def __init__(
        self,
        session_id: str,
        scenario_generator: ScenarioGenerator,
        feedback_engine: FeedbackEngine,
    ):
        self.session_id = session_id
        self.generator = scenario_generator
        self.feedback_engine = feedback_engine
        
        self.stats = SessionStats(
            session_id=session_id,
            start_time=datetime.now(),
        )
        
        self.attempts: list[Attempt] = []
        self.current_scenario: Optional[Scenario] = None
    
    def start_scenario(self, difficulty: int = 1) -> Scenario:
        """Start a new scenario."""
        self.current_scenario = self.generator.generate_random_scenario(difficulty)
        self.stats.total_scenarios += 1
        return self.current_scenario
    
    def submit_action(self, action: str, time_taken_ms: int = 0) -> Feedback:
        """Submit an action for the current scenario."""
        if not self.current_scenario:
            raise ValueError("No active scenario")
        
        # Get feedback
        feedback = self.feedback_engine.analyze_decision(
            self.current_scenario, action
        )
        
        # Record attempt
        attempt = Attempt(
            scenario_id=self.current_scenario.scenario_id,
            player_action=action,
            feedback=feedback,
            time_taken_ms=time_taken_ms,
        )
        self.attempts.append(attempt)
        
        # Update stats
        if feedback.feedback_type == FeedbackType.CORRECT:
            self.stats.correct += 1
        elif feedback.feedback_type == FeedbackType.CLOSE:
            self.stats.close += 1
        else:
            self.stats.incorrect += 1
        
        self.stats.total_time_ms += time_taken_ms
        if self.stats.total_scenarios > 0:
            self.stats.avg_time_ms = self.stats.total_time_ms // self.stats.total_scenarios
        
        # Calculate accuracy
        total = self.stats.correct + self.stats.close + self.stats.incorrect
        if total > 0:
            self.stats.accuracy = (self.stats.correct + self.stats.close * 0.5) / total
        
        return feedback
    
    def end_session(self) -> SessionStats:
        """End the current session."""
        self.stats.end_time = datetime.now()
        
        # Calculate by-situation stats
        situation_counts = defaultdict(lambda: {"correct": 0, "total": 0})
        for attempt in self.attempts:
            # Would need scenario tags - simplified here
            pass
        
        return self.stats


class SessionManager:
    """Manages training sessions and progress."""
    
    def __init__(self, db_path: str = ":memory:"):
        """Initialize session manager."""
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        
        self.feedback_engine = FeedbackEngine()
        self.scenario_generator = ScenarioGenerator()
    
    def _create_tables(self):
        """Create database tables."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                start_time TEXT,
                end_time TEXT,
                total_scenarios INTEGER,
                correct INTEGER,
                close INTEGER,
                incorrect INTEGER,
                accuracy REAL,
                avg_ev_loss REAL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                scenario_id TEXT,
                player_action TEXT,
                feedback_type TEXT,
                ev_loss REAL,
                time_taken_ms INTEGER,
                timestamp TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scenario_progress (
                scenario_id TEXT PRIMARY KEY,
                attempts INTEGER,
                correct INTEGER,
                avg_ev_loss REAL,
                ease_factor REAL,
                interval_days REAL,
                next_review TEXT
            )
        """)
        
        self.conn.commit()
    
    def create_session(self) -> TrainingSession:
        """Create a new training session."""
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        session = TrainingSession(
            session_id=session_id,
            scenario_generator=self.scenario_generator,
            feedback_engine=self.feedback_engine,
        )
        
        return session
    
    def save_session(self, session: TrainingSession):
        """Save session to database."""
        cursor = self.conn.cursor()
        
        # Save session
        cursor.execute("""
            INSERT OR REPLACE INTO sessions
            (session_id, start_time, end_time, total_scenarios, correct, close, incorrect, accuracy, avg_ev_loss)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.session_id,
            session.stats.start_time.isoformat(),
            session.stats.end_time.isoformat() if session.stats.end_time else None,
            session.stats.total_scenarios,
            session.stats.correct,
            session.stats.close,
            session.stats.incorrect,
            session.stats.accuracy,
            session.stats.avg_ev_loss,
        ))
        
        # Save attempts
        for attempt in session.attempts:
            cursor.execute("""
                INSERT INTO attempts
                (session_id, scenario_id, player_action, feedback_type, ev_loss, time_taken_ms, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session.session_id,
                attempt.scenario_id,
                attempt.player_action,
                attempt.feedback.feedback_type.value,
                attempt.feedback.ev_loss,
                attempt.time_taken_ms,
                attempt.timestamp.isoformat(),
            ))
        
        self.conn.commit()
    
    def get_session_stats(self, session_id: str) -> Optional[dict]:
        """Get stats for a session."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_player_stats(self) -> dict:
        """Get overall player statistics."""
        cursor = self.conn.cursor()
        
        # Total sessions
        cursor.execute("SELECT COUNT(*) as total FROM sessions")
        total_sessions = cursor.fetchone()["total"]
        
        # Total attempts
        cursor.execute("SELECT COUNT(*) as total FROM attempts")
        total_attempts = cursor.fetchone()["total"]
        
        # Accuracy
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN feedback_type = 'correct' THEN 1 ELSE 0 END) as correct,
                SUM(CASE WHEN feedback_type = 'close' THEN 1 ELSE 0 END) as close,
                COUNT(*) as total
            FROM attempts
        """)
        accuracy_row = cursor.fetchone()
        
        correct = accuracy_row["correct"] or 0
        close = accuracy_row["close"] or 0
        total = accuracy_row["total"] or 1
        
        accuracy = (correct + close * 0.5) / total
        
        # Average EV loss
        cursor.execute("SELECT AVG(ev_loss) as avg FROM attempts")
        avg_ev_loss = cursor.fetchone()["avg"] or 0
        
        # Recent sessions
        cursor.execute("""
            SELECT * FROM sessions 
            ORDER BY start_time DESC 
            LIMIT 5
        """)
        recent = [dict(row) for row in cursor.fetchall()]
        
        return {
            "total_sessions": total_sessions,
            "total_attempts": total_attempts,
            "accuracy": accuracy,
            "avg_ev_loss": avg_ev_loss,
            "recent_sessions": recent,
        }
    
    def get_scenario_progress(self, scenario_id: str) -> Optional[dict]:
        """Get progress on a specific scenario."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM scenario_progress WHERE scenario_id = ?",
            (scenario_id,)
        )
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_scenarios_for_review(self, limit: int = 10) -> list[str]:
        """Get scenarios that need review based on spaced repetition."""
        cursor = self.conn.cursor()
        
        now = datetime.now().isoformat()
        cursor.execute("""
            SELECT scenario_id FROM scenario_progress
            WHERE next_review <= ?
            ORDER BY next_review ASC
            LIMIT ?
        """, (now, limit))
        
        return [row["scenario_id"] for row in cursor.fetchall()]
    
    def update_scenario_progress(
        self,
        scenario_id: str,
        correct: bool,
        ev_loss: float,
    ):
        """Update progress on a scenario using SM-2 algorithm."""
        cursor = self.conn.cursor()
        
        # Get current progress
        cursor.execute(
            "SELECT * FROM scenario_progress WHERE scenario_id = ?",
            (scenario_id,)
        )
        row = cursor.fetchone()
        
        if row:
            # Update existing
            attempts = row["attempts"] + 1
            correct_count = row["correct"] + (1 if correct else 0)
            avg_ev_loss = (row["avg_ev_loss"] * row["attempts"] + ev_loss) / attempts
            
            # SM-2 algorithm
            ease_factor = row["ease_factor"]
            interval_days = row["interval_days"]
            
            if correct:
                if attempts == 1:
                    interval_days = 1
                elif attempts == 2:
                    interval_days = 6
                else:
                    interval_days = interval_days * ease_factor
                ease_factor = max(1.3, ease_factor + 0.1)
            else:
                interval_days = 1
                ease_factor = max(1.3, ease_factor - 0.2)
            
            next_review = datetime.now() + timedelta(days=interval_days)
            
            cursor.execute("""
                UPDATE scenario_progress
                SET attempts = ?, correct = ?, avg_ev_loss = ?,
                    ease_factor = ?, interval_days = ?, next_review = ?
                WHERE scenario_id = ?
            """, (attempts, correct_count, avg_ev_loss, ease_factor, interval_days,
                  next_review.isoformat(), scenario_id))
        else:
            # Create new
            next_review = datetime.now() + timedelta(days=1)
            cursor.execute("""
                INSERT INTO scenario_progress
                (scenario_id, attempts, correct, avg_ev_loss, ease_factor, interval_days, next_review)
                VALUES (?, 1, ?, ?, 2.5, 1.0, ?)
            """, (scenario_id, 1 if correct else 0, ev_loss, next_review.isoformat()))
        
        self.conn.commit()
    
    def close(self):
        """Close the database connection."""
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
