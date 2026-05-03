"""Tests for MDA (Mass Data Analysis) module."""

import pytest
from datetime import datetime

from mda.parser import HandHistory, parse_hand_history, Street, Action
from mda.storage import HandHistoryStore
from mda.profiler import PlayerProfiler, PlayStyle
from mda.analyzer import PopulationAnalyzer


# Sample PokerStars hand history
SAMPLE_HAND = """PokerStars Hand #123456789: Hold'em No Limit ($1/$2 USD) - 2024/01/01 12:00:00 ET
Table 'Test' 6-max Seat #1 is the button
Seat 1: Player1 ($200 in chips)
Seat 2: Player2 ($200 in chips)
Player1: posts small blind $1
Player2: posts big blind $2
*** HOLE CARDS ***
Dealt to Player1 [Ah Kd]
Player1: raises $4 to $6
Player2: calls $4
*** FLOP *** [7h 8c 9d]
Player2: checks
Player1: bets $8
Player2: folds
Player1 collected $12 from pot
*** SUMMARY ***
Total pot $12 | Rake $0
Board [7h 8c 9d]
Seat 1: Player1 ($12) (button) (small blind)
Seat 2: Player2 (folded)"""


class TestParser:
    """Tests for hand history parser."""
    
    def test_parse_basic_hand(self):
        """Should parse a basic hand history."""
        hand = parse_hand_history(SAMPLE_HAND)
        
        assert hand.hand_id == "123456789"
        assert hand.max_seats == 6
        assert hand.button_seat == 1
        assert "Player1" in hand.players
        assert "Player2" in hand.players
        assert hand.players["Player1"] == 200
        assert hand.players["Player2"] == 200
    
    def test_parse_blinds(self):
        """Should parse blind amounts."""
        hand = parse_hand_history(SAMPLE_HAND)
        
        assert hand.blinds == (1.0, 2.0)
    
    def test_parse_board(self):
        """Should parse board cards."""
        hand = parse_hand_history(SAMPLE_HAND)
        
        assert len(hand.board) == 3
        assert "7h" in hand.board
        assert "8c" in hand.board
        assert "9d" in hand.board
    
    def test_parse_actions(self):
        """Should parse player actions."""
        hand = parse_hand_history(SAMPLE_HAND)
        
        # Should have preflop and flop actions
        preflop_actions = [a for a in hand.actions if a.street == Street.PREFLOP]
        flop_actions = [a for a in hand.actions if a.street == Street.FLOP]
        
        assert len(preflop_actions) >= 2
        assert len(flop_actions) >= 2
    
    def test_parse_winners(self):
        """Should parse winner information."""
        hand = parse_hand_history(SAMPLE_HAND)
        
        assert "Player1" in hand.winners
        assert hand.winners["Player1"] == 12.0
    
    def test_parse_pot(self):
        """Should parse pot size."""
        hand = parse_hand_history(SAMPLE_HAND)
        
        assert hand.pot == 12.0


class TestStorage:
    """Tests for hand history storage."""
    
    @pytest.fixture
    def store(self):
        """Create in-memory store."""
        store = HandHistoryStore(":memory:")
        yield store
        store.close()
    
    def test_add_hand(self, store):
        """Should add hand to store."""
        hand = parse_hand_history(SAMPLE_HAND)
        store.add_hand(hand)
        
        # Verify stored
        cursor = store.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM hands")
        assert cursor.fetchone()[0] == 1
    
    def test_get_player_stats(self, store):
        """Should calculate player stats."""
        hand = parse_hand_history(SAMPLE_HAND)
        store.add_hand(hand)
        
        stats = store.get_player_stats("Player1")
        
        assert stats["total_hands"] == 1
        assert "vpip" in stats
        assert "pfr" in stats
    
    def test_get_player_hands(self, store):
        """Should get hands for a player."""
        hand = parse_hand_history(SAMPLE_HAND)
        store.add_hand(hand)
        
        hands = store.get_player_hands("Player1")
        assert len(hands) == 1
    
    def test_multiple_hands(self, store):
        """Should handle multiple hands."""
        for i in range(5):
            hand = parse_hand_history(SAMPLE_HAND)
            hand.hand_id = str(123456789 + i)
            store.add_hand(hand)
        
        stats = store.get_player_stats("Player1")
        assert stats["total_hands"] == 5


class TestProfiler:
    """Tests for player profiler."""
    
    @pytest.fixture
    def store_with_data(self):
        """Create store with sample data."""
        store = HandHistoryStore(":memory:")
        
        # Add multiple hands for reliable stats
        for i in range(10):
            hand = parse_hand_history(SAMPLE_HAND)
            hand.hand_id = str(123456789 + i)
            store.add_hand(hand)
        
        yield store
        store.close()
    
    def test_profile_player(self, store_with_data):
        """Should create player profile."""
        profiler = PlayerProfiler(store_with_data)
        profile = profiler.profile_player("Player1", min_hands=5)
        
        assert profile is not None
        assert profile.player_name == "Player1"
        assert profile.total_hands == 10
    
    def test_classify_style(self, store_with_data):
        """Should classify player style."""
        profiler = PlayerProfiler(store_with_data)
        profile = profiler.profile_player("Player1", min_hands=5)
        
        assert profile.style != PlayStyle.UNKNOWN
    
    def test_insufficient_data(self, store_with_data):
        """Should return None for insufficient data."""
        profiler = PlayerProfiler(store_with_data)
        profile = profiler.profile_player("NewPlayer", min_hands=100)
        
        assert profile is None


class TestAnalyzer:
    """Tests for population analyzer."""
    
    @pytest.fixture
    def store_with_data(self):
        """Create store with sample data."""
        store = HandHistoryStore(":memory:")
        
        # Add hands
        for i in range(10):
            hand = parse_hand_history(SAMPLE_HAND)
            hand.hand_id = str(123456789 + i)
            store.add_hand(hand)
        
        yield store
        store.close()
    
    def test_analyze_preflop_open(self, store_with_data):
        """Should analyze preflop opening tendencies."""
        analyzer = PopulationAnalyzer(store_with_data)
        report = analyzer.analyze_preflop_open("BTN")
        
        assert report.situation == "preflop_open_BTN"
        assert isinstance(report.tendencies, list)
    
    def test_analyze_bb_defend(self, store_with_data):
        """Should analyze BB defense tendencies."""
        analyzer = PopulationAnalyzer(store_with_data)
        report = analyzer.analyze_bb_defend()
        
        assert report.situation == "bb_defend"
    
    def test_get_population_summary(self, store_with_data):
        """Should get population summary."""
        analyzer = PopulationAnalyzer(store_with_data)
        summary = analyzer.get_population_summary()
        
        assert "total_hands" in summary
        assert "total_players" in summary
