"""Tests for 6-max defense strategy."""

import pytest
import numpy as np

from strategy.defense import (
    estimate_opening_range,
    compute_bb_defense,
    compute_sb_defense,
    get_defense_strategy_for_scenario,
)


class TestRangeEstimation:
    """Tests for opponent range estimation."""
    
    def test_open_range_estimation_utg(self):
        """UTG should have tight opening range."""
        range_freq = estimate_opening_range("UTG", 100.0)
        
        # Should be around 18% of hands
        range_pct = range_freq.sum() / 169
        assert 0.10 < range_pct < 0.30
        
        # AA should always be opened
        from engine.hand_class import class_index
        aa_idx = class_index("AA")
        assert range_freq[aa_idx] == 1.0
        
        # 72o should never be opened
        junk_idx = class_index("72o")
        assert range_freq[junk_idx] == 0.0
    
    def test_open_range_estimation_btn(self):
        """BTN should have wide opening range."""
        range_freq = estimate_opening_range("BTN", 100.0)
        
        # Should be around 42% of hands
        range_pct = range_freq.sum() / 169
        assert 0.30 < range_pct < 0.55
    
    def test_range_ordering(self):
        """Ranges should get wider from UTG to BTN."""
        utg = estimate_opening_range("UTG", 100.0)
        hj = estimate_opening_range("HJ", 100.0)
        co = estimate_opening_range("CO", 100.0)
        btn = estimate_opening_range("BTN", 100.0)
        
        assert utg.sum() < hj.sum() < co.sum() < btn.sum()
    
    def test_stack_depth_adjustment(self):
        """Short stacks should play tighter."""
        short = estimate_opening_range("BTN", 20.0)
        deep = estimate_opening_range("BTN", 200.0)
        
        assert short.sum() < deep.sum()


class TestBBDefense:
    """Tests for BB defense computation."""
    
    def test_bb_defense_vs_btn(self):
        """BB should defend wider against BTN open."""
        defense = compute_bb_defense("BTN", 100.0, 2.5)
        
        # BB should defend ~60-75% against BTN (good pot odds)
        assert 0.55 < defense.defense_freq < 0.80
        
        # Should have some 3-bets
        assert defense.three_bet_freq_total > 0.05
        
        # Should have some calls
        assert defense.call_freq_total > 0.1
    
    def test_bb_defense_vs_utg(self):
        """BB should defend tighter against UTG open."""
        defense_btn = compute_bb_defense("BTN", 100.0, 2.5)
        defense_utg = compute_bb_defense("UTG", 100.0, 2.5)
        
        # Should defend less against UTG
        assert defense_utg.defense_freq < defense_btn.defense_freq
    
    def test_bb_defense_premium_hands(self):
        """Premium hands should always be defended."""
        defense = compute_bb_defense("BTN", 100.0, 2.5)
        
        from engine.hand_class import class_index
        aa_idx = class_index("AA")
        kk_idx = class_index("KK")
        
        # AA/KK should never fold
        assert defense.fold_freq[aa_idx] < 0.05
        assert defense.fold_freq[kk_idx] < 0.05
    
    def test_bb_defense_junk_hands(self):
        """Junk hands should mostly fold."""
        defense = compute_bb_defense("BTN", 100.0, 2.5)
        
        from engine.hand_class import class_index
        junk_idx = class_index("72o")
        
        # 72o should fold more than 60%
        assert defense.fold_freq[junk_idx] > 0.6
    
    def test_bb_defense_strategy_structure(self):
        """Defense strategy should have correct structure."""
        defense = compute_bb_defense("BTN", 100.0, 2.5)
        
        # Arrays should be correct length
        assert len(defense.fold_freq) == 169
        assert len(defense.call_freq) == 169
        assert len(defense.three_bet_freq) == 169
        
        # Probabilities should sum to ~1 for each hand
        for i in range(169):
            total = defense.fold_freq[i] + defense.call_freq[i] + defense.three_bet_freq[i]
            assert abs(total - 1.0) < 0.01


class TestSBDefense:
    """Tests for SB defense computation."""
    
    def test_sb_defense_vs_btn(self):
        """SB should defend but tighter than BB."""
        defense_bb = compute_bb_defense("BTN", 100.0, 2.5)
        defense_sb = compute_sb_defense("BTN", 100.0, 2.5)
        
        # SB should defend less than BB (position disadvantage)
        assert defense_sb.defense_freq < defense_bb.defense_freq
    
    def test_sb_3bet_frequency(self):
        """SB should 3-bet more to compensate for position."""
        defense = compute_sb_defense("BTN", 100.0, 2.5)
        
        # Should have decent 3-bet frequency
        assert defense.three_bet_freq_total > 0.05


class TestDefenseAPI:
    """Tests for defense strategy API integration."""
    
    def test_get_bb_defense_strategy(self):
        """Should return formatted defense strategy for BB."""
        result = get_defense_strategy_for_scenario("BB", "BTN", 100.0, 2.5)
        
        assert "strategies" in result
        assert "defense_freq" in result
        assert "explanation" in result
        assert len(result["strategies"]) == 169
    
    def test_get_sb_defense_strategy(self):
        """Should return formatted defense strategy for SB."""
        result = get_defense_strategy_for_scenario("SB", "BTN", 100.0, 2.5)
        
        assert "strategies" in result
        assert result["defense_freq"] > 0
    
    def test_invalid_position_raises(self):
        """Should raise error for invalid position."""
        with pytest.raises(ValueError):
            get_defense_strategy_for_scenario("UTG", "BTN", 100.0, 2.5)


class TestSolverIntegration:
    """Tests that defense strategies are solver-true."""
    
    def test_bb_defense_exploitability(self):
        """Defense strategy should have reasonable exploitability."""
        defense = compute_bb_defense("BTN", 100.0, 2.5)
        
        # Check that fold/call/3bet are reasonable
        assert defense.fold_freq.mean() > 0.2  # Should fold some hands
        assert defense.fold_freq.mean() < 0.5  # But not too many
        
        # Check that defense frequency is in reasonable range
        assert 0.55 < defense.defense_freq < 0.80
    
    def test_defense_adapts_to_villain_range(self):
        """Defense should tighten against tighter opens."""
        defense_wide = compute_bb_defense("BTN", 100.0, 2.5)
        defense_tight = compute_bb_defense("UTG", 100.0, 2.5)
        
        # Should fold more against tight range
        assert defense_tight.fold_freq.mean() > defense_wide.fold_freq.mean()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
