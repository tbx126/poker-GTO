"""Tests for GTO Trainer module."""

import pytest
from datetime import datetime

from trainer.scenario import Scenario, ScenarioGenerator, SituationType
from trainer.feedback import Feedback, FeedbackEngine, FeedbackType
from trainer.session import TrainingSession, SessionManager
from trainer.leak_detector import LeakDetector, LeakReport


class TestScenarioGenerator:
    """Tests for scenario generator."""
    
    @pytest.fixture
    def generator(self):
        """Create scenario generator."""
        return ScenarioGenerator()
    
    def test_generate_preflop_open(self, generator):
        """Should generate preflop open scenario."""
        scenario = generator.generate_preflop_open("BTN", 100)
        
        assert scenario.situation_type == SituationType.PREFLOP_OPEN
        assert len(scenario.actions) > 0
        assert scenario.stacks == (100, 100)
    
    def test_generate_preflop_3bet(self, generator):
        """Should generate preflop 3-bet scenario."""
        scenario = generator.generate_preflop_3bet()
        
        assert scenario.situation_type == SituationType.PREFLOP_3BET
        assert "3-bet" in scenario.description.lower() or "3bet" in scenario.description.lower()
    
    def test_generate_flop_cbet(self, generator):
        """Should generate flop cbet scenario."""
        scenario = generator.generate_flop_cbet("dry")
        
        assert scenario.situation_type == SituationType.FLOP_CBET
        assert len(scenario.board) == 3
    
    def test_generate_river_call(self, generator):
        """Should generate river call scenario."""
        scenario = generator.generate_river_call("pot")
        
        assert scenario.situation_type == SituationType.RIVER_CALL
        assert len(scenario.board) == 5
    
    def test_generate_random_scenario(self, generator):
        """Should generate random scenario."""
        scenario = generator.generate_random_scenario(1)
        
        assert isinstance(scenario, Scenario)
        assert scenario.scenario_id is not None
    
    def test_generate_training_set(self, generator):
        """Should generate multiple scenarios."""
        scenarios = generator.generate_training_set(5, 1)
        
        assert len(scenarios) == 5
        assert all(isinstance(s, Scenario) for s in scenarios)


class TestFeedbackEngine:
    """Tests for feedback engine."""
    
    @pytest.fixture
    def engine(self):
        """Create feedback engine."""
        return FeedbackEngine(tolerance=0.1)
    
    @pytest.fixture
    def sample_scenario(self):
        """Create sample scenario."""
        return Scenario(
            scenario_id="test_001",
            situation_type=SituationType.PREFLOP_OPEN,
            description="Test scenario",
            stacks=(100, 100),
            pot=3,
            actions=["fold", "open", "shove"],
            gto_strategy={"fold": 0.2, "open": 0.7, "shove": 0.1},
        )
    
    def test_correct_action(self, engine, sample_scenario):
        """Should identify correct action."""
        feedback = engine.analyze_decision(sample_scenario, "open")
        
        assert feedback.feedback_type == FeedbackType.CORRECT
        assert feedback.ev_loss == 0.0
    
    def test_close_action(self, engine, sample_scenario):
        """Should identify close action."""
        feedback = engine.analyze_decision(sample_scenario, "fold")
        
        assert feedback.feedback_type == FeedbackType.CLOSE
    
    def test_incorrect_action(self, engine, sample_scenario):
        """Should identify incorrect action."""
        feedback = engine.analyze_decision(sample_scenario, "invalid_action")
        
        assert feedback.feedback_type == FeedbackType.INCORRECT
    
    def test_batch_analyze(self, engine, sample_scenario):
        """Should analyze multiple decisions."""
        scenarios = [sample_scenario] * 3
        actions = ["open", "fold", "shove"]
        
        feedbacks = engine.batch_analyze(scenarios, actions)
        
        assert len(feedbacks) == 3
    
    def test_calculate_accuracy(self, engine, sample_scenario):
        """Should calculate accuracy metrics."""
        scenarios = [sample_scenario] * 4
        actions = ["open", "open", "fold", "shove"]
        
        feedbacks = engine.batch_analyze(scenarios, actions)
        accuracy = engine.calculate_accuracy(feedbacks)
        
        assert "accuracy" in accuracy
        assert "total" in accuracy
        assert accuracy["total"] == 4


class TestSessionManager:
    """Tests for session manager."""
    
    @pytest.fixture
    def manager(self):
        """Create session manager."""
        return SessionManager(":memory:")
    
    def test_create_session(self, manager):
        """Should create training session."""
        session = manager.create_session()
        
        assert isinstance(session, TrainingSession)
        assert session.session_id is not None
    
    def test_training_flow(self, manager):
        """Should handle complete training flow."""
        session = manager.create_session()
        
        # Start scenario
        scenario = session.start_scenario(1)
        assert isinstance(scenario, Scenario)
        
        # Submit action
        feedback = session.submit_action("open", 1000)
        assert isinstance(feedback, Feedback)
        
        # End session
        stats = session.end_session()
        assert stats.total_scenarios == 1
    
    def test_save_session(self, manager):
        """Should save session to database."""
        session = manager.create_session()
        session.start_scenario(1)
        session.submit_action("open", 1000)
        session.end_session()
        
        manager.save_session(session)
        
        # Verify saved
        stats = manager.get_session_stats(session.session_id)
        assert stats is not None
    
    def test_get_player_stats(self, manager):
        """Should get player statistics."""
        # Create and save a session
        session = manager.create_session()
        session.start_scenario(1)
        session.submit_action("open", 1000)
        session.end_session()
        manager.save_session(session)
        
        stats = manager.get_player_stats()
        
        assert "total_sessions" in stats
        assert "accuracy" in stats
    
    def test_spaced_repetition(self, manager):
        """Should update scenario progress."""
        manager.update_scenario_progress("scenario_001", True, 0.0)
        
        progress = manager.get_scenario_progress("scenario_001")
        assert progress is not None
        assert progress["attempts"] == 1


class TestLeakDetector:
    """Tests for leak detector."""
    
    @pytest.fixture
    def store_with_leaks(self):
        """Create store with leak-inducing data."""
        from mda.storage import HandHistoryStore
        from mda.parser import parse_hand_history
        
        store = HandHistoryStore(":memory:")
        
        # Create hands with passive play
        sample_hand = """PokerStars Hand #123456789: Hold'em No Limit ($1/$2 USD) - 2024/01/01 12:00:00 ET
Table 'Test' 6-max Seat #1 is the button
Seat 1: Player1 ($200 in chips)
Seat 2: Player2 ($200 in chips)
Player1: posts small blind $1
Player2: posts big blind $2
*** HOLE CARDS ***
Dealt to Player1 [Ah Kd]
Player1: calls $1
Player2: checks
*** FLOP *** [7h 8c 9d]
Player2: checks
Player1: checks
*** TURN *** [2c]
Player2: checks
Player1: checks
*** RIVER *** [5s]
Player2: bets $4
Player1: folds
*** SUMMARY ***
Total pot $4 | Rake $0
Board [7h 8c 9d 2c 5s]
Seat 1: Player1 (folded)
Seat 2: Player2 ($4)"""
        
        for i in range(20):
            hand = parse_hand_history(sample_hand)
            hand.hand_id = str(123456789 + i)
            store.add_hand(hand)
        
        yield store
        store.close()
    
    def test_detect_leaks(self, store_with_leaks):
        """Should detect leaks."""
        detector = LeakDetector(store_with_leaks)
        report = detector.detect_leaks("Player1", min_hands=10)
        
        assert isinstance(report, LeakReport)
        assert report.player_name == "Player1"
        assert report.total_hands == 20
    
    def test_leak_report_structure(self, store_with_leaks):
        """Should have proper leak report structure."""
        detector = LeakDetector(store_with_leaks)
        report = detector.detect_leaks("Player1", min_hands=10)
        
        assert isinstance(report.leaks, list)
        assert isinstance(report.total_ev_loss, float)
        assert isinstance(report.priority_training, list)
    
    def test_sample_leak_report(self, store_with_leaks):
        """Should generate sample leak report."""
        detector = LeakDetector(store_with_leaks)
        report = detector.generate_sample_leak_report()
        
        assert len(report.leaks) > 0
        assert report.total_ev_loss > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
