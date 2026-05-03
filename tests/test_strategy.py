"""Tests for multi-table strategy module."""

import pytest

from strategy.positions import (
    Position,
    get_position_name,
    get_position_description,
    get_relative_position,
)
from strategy.ranges import (
    OpeningRange,
    ThreeBetRange,
    get_opening_range,
    get_3bet_range,
)
from strategy.scenarios import (
    TableScenario,
    ScenarioAnalysis,
    analyze_scenario,
    get_scenario_description,
)


class TestPositions:
    """Tests for position definitions."""
    
    def test_position_names(self):
        """Should have names for all positions."""
        for pos in Position:
            name = get_position_name(pos)
            assert len(name) > 0
    
    def test_position_descriptions(self):
        """Should have descriptions for all positions."""
        for pos in Position:
            desc = get_position_description(pos)
            assert len(desc) > 0
    
    def test_relative_position_ip(self):
        """BTN should always be in position."""
        assert get_relative_position(Position.BTN, Position.SB) == "IP"
        assert get_relative_position(Position.BTN, Position.BB) == "IP"
        assert get_relative_position(Position.BTN, Position.UTG) == "IP"
    
    def test_relative_position_oop(self):
        """BB should be out of position against most positions."""
        assert get_relative_position(Position.BB, Position.BTN) == "OOP"
        assert get_relative_position(Position.BB, Position.CO) == "OOP"
        # SB vs BTN - BTN has position
        assert get_relative_position(Position.SB, Position.BTN) == "OOP"
    
    def test_co_vs_btn(self):
        """CO should be OOP against BTN."""
        assert get_relative_position(Position.CO, Position.BTN) == "OOP"
    
    def test_co_vs_hj(self):
        """CO should be IP against HJ."""
        assert get_relative_position(Position.CO, Position.HJ) == "IP"


class TestRanges:
    """Tests for opening and 3-bet ranges."""
    
    def test_utg_range_tight(self):
        """UTG range should be tight."""
        rng = get_opening_range(Position.UTG, 100.0, 6)
        
        # Strong hands should be in range
        assert rng.hands.get("AA", 0) == 1.0
        assert rng.hands.get("KK", 0) == 1.0
        assert rng.hands.get("AKs", 0) == 1.0
        
        # Weak hands should not be in range
        assert rng.hands.get("72o", 0) == 0.0
        assert rng.hands.get("83s", 0) == 0.0
    
    def test_btn_range_wide(self):
        """BTN range should be wide."""
        rng = get_opening_range(Position.BTN, 100.0, 6)
        
        # Should have high VPIP
        assert rng.vpip > 0.4
        
        # Most pairs should be in range
        assert rng.hands.get("22", 0) > 0.5
        
        # Many suited hands should be in range
        assert rng.hands.get("76s", 0) > 0.5
    
    def test_range_ordering(self):
        """BTN range should be wider than UTG."""
        utg = get_opening_range(Position.UTG, 100.0, 6)
        btn = get_opening_range(Position.BTN, 100.0, 6)
        
        # BTN should have significantly more hands
        utg_hands = sum(1 for f in utg.hands.values() if f > 0.5)
        btn_hands = sum(1 for f in btn.hands.values() if f > 0.5)
        assert btn_hands > utg_hands
    
    def test_3bet_range_value(self):
        """Should have value 3-bet hands."""
        rng = get_3bet_range(Position.CO, Position.UTG, 100.0)
        
        # Premium hands should be value 3-bets
        assert rng.value_hands.get("AA", 0) == 1.0
        assert rng.value_hands.get("KK", 0) == 1.0
        assert rng.value_hands.get("AKs", 0) == 1.0
    
    def test_3bet_range_bluff(self):
        """Should have bluff 3-bet hands against late position."""
        rng = get_3bet_range(Position.BB, Position.BTN, 100.0)
        
        # Should have some bluff hands
        bluff_count = sum(1 for f in rng.bluff_hands.values() if f > 0)
        assert bluff_count > 0
    
    def test_3bet_vs_early_tight(self):
        """3-bet range should be tighter against early position."""
        vs_utg = get_3bet_range(Position.CO, Position.UTG, 100.0)
        vs_btn = get_3bet_range(Position.CO, Position.BTN, 100.0)
        
        # Less bluffing against UTG
        utg_bluffs = sum(vs_utg.bluff_hands.values())
        btn_bluffs = sum(vs_btn.bluff_hands.values())
        assert utg_bluffs < btn_bluffs


class TestScenarios:
    """Tests for scenario analysis."""
    
    def test_open_scenario(self):
        """Should analyze opening scenario."""
        scenario = TableScenario(
            table_size=6,
            hero_position=Position.BTN,
            hero_hand="AKs",
        )
        
        analysis = analyze_scenario(scenario)
        
        assert analysis.recommended_action.value.startswith("raise")
        assert analysis.hand_in_range
    
    def test_face_open_scenario(self):
        """Should analyze facing open scenario."""
        scenario = TableScenario(
            table_size=6,
            hero_position=Position.BB,
            hero_hand="KQs",
            raiser_position=Position.BTN,
            raise_size=2.5,
        )
        
        analysis = analyze_scenario(scenario)
        
        assert analysis.hand_in_range
        assert "call" in analysis.action_frequencies or "3bet" in str(analysis.action_frequencies)
    
    def test_face_3bet_scenario(self):
        """Should analyze facing 3-bet scenario."""
        scenario = TableScenario(
            table_size=6,
            hero_position=Position.BTN,
            hero_hand="AA",
            raiser_position=Position.HJ,
            raise_size=2.5,
            three_bettor=Position.CO,
            three_bet_size=9.0,
        )
        
        analysis = analyze_scenario(scenario)
        
        # AA should 4-bet (raise_4x) or all-in
        assert "4bet" in analysis.recommended_action.value or "raise_4x" in analysis.recommended_action.value or "all_in" in analysis.recommended_action.value
    
    def test_scenario_description(self):
        """Should generate readable description."""
        scenario = TableScenario(
            table_size=6,
            hero_position=Position.BTN,
            hero_hand="AKs",
        )
        
        desc = get_scenario_description(scenario)
        
        assert "BTN" in desc
        assert "AKs" in desc
    
    def test_premium_hand_always_raise(self):
        """AA should always be raised/4-bet."""
        # Opening
        scenario = TableScenario(
            table_size=6,
            hero_position=Position.UTG,
            hero_hand="AA",
        )
        analysis = analyze_scenario(scenario)
        assert analysis.recommended_action.value.startswith("raise")
        
        # Facing 3-bet
        scenario = TableScenario(
            table_size=6,
            hero_position=Position.BTN,
            hero_hand="AA",
            raiser_position=Position.HJ,
            raise_size=2.5,
            three_bettor=Position.CO,
            three_bet_size=9.0,
        )
        analysis = analyze_scenario(scenario)
        assert analysis.hand_in_range
    
    def test_junk_hand_fold(self):
        """72o should always fold."""
        # Opening from UTG
        scenario = TableScenario(
            table_size=6,
            hero_position=Position.UTG,
            hero_hand="72o",
        )
        analysis = analyze_scenario(scenario)
        assert not analysis.hand_in_range
        assert analysis.recommended_action.value == "fold"


class TestAPIIntegration:
    """Test API integration."""
    
    def test_analyze_endpoint(self):
        """Should work with API service."""
        from api.service import analyze_table_scenario
        
        result = analyze_table_scenario(
            table_size=6,
            effective_stack=100.0,
            ante=0.0,
            hero_position="BTN",
            hero_hand="AKs",
        )
        
        assert result.recommended_action.startswith("raise")
        assert result.hand_in_range
    
    def test_range_endpoint(self):
        """Should get opening range."""
        from api.service import get_position_opening_range
        
        result = get_position_opening_range("BTN", 100.0, 6)
        
        assert result.position == "BTN"
        assert result.vpip > 0.3
        assert len(result.hands) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
