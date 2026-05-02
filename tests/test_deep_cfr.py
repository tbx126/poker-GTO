"""Tests for Deep CFR module."""

import numpy as np
import pytest
import torch

from engine.actions import ActionKind
from solver.deep_cfr.encoder import (
    GroupedTokenEncoder,
    GameStateEncoder,
    extract_raw_features,
)
from solver.deep_cfr.network import (
    AdvantageNetwork,
    MLPBackbone,
    RegretMatching,
    StrategyNetwork,
    TransformerBackbone,
    ValueNetwork,
)


class TestEncoder:
    """Tests for feature encoders."""
    
    def test_mlp_backbone_output_shape(self):
        """MLP backbone should output correct shape."""
        backbone = MLPBackbone(input_dim=141, hidden_dims=[64, 32])
        x = torch.randn(4, 141)
        out = backbone(x)
        assert out.shape == (4, 32)
    
    def test_transformer_backbone_output_shape(self):
        """Transformer backbone should output correct shape."""
        backbone = TransformerBackbone(token_dim=64, num_heads=4, num_layers=2)
        x = torch.randn(4, 31, 64)  # 31 tokens
        out = backbone(x)
        assert out.shape == (4, 64)
    
    def test_grouped_token_encoder_output_shape(self):
        """GroupedTokenEncoder should output correct token sequence."""
        encoder = GroupedTokenEncoder(token_dim=64)
        
        # Create dummy inputs
        cards = torch.randn(4, 9, 17)
        round_tok = torch.randn(4, 1, 4)
        state_tok = torch.randn(4, 1, 22)
        act_tok = torch.randn(4, 20, 10)
        
        tokens = encoder(cards, round_tok, state_tok, act_tok)
        assert tokens.shape == (4, 31, 64)


class TestNetwork:
    """Tests for neural networks."""
    
    def test_value_network_mlp(self):
        """ValueNetwork with MLP should output correct shape."""
        net = ValueNetwork(num_actions=5, backbone_type="mlp")
        x = torch.randn(4, 141)
        out = net(x)
        assert out.shape == (4, 5)
    
    def test_value_network_transformer(self):
        """ValueNetwork with transformer should output correct shape."""
        net = ValueNetwork(num_actions=5, backbone_type="transformer")
        x = torch.randn(4, 31, 64)
        out = net(x)
        assert out.shape == (4, 5)
    
    def test_strategy_network_outputs_probabilities(self):
        """StrategyNetwork should output valid probabilities."""
        net = StrategyNetwork(num_actions=5, backbone_type="mlp")
        x = torch.randn(4, 141)
        probs = net(x)
        
        assert probs.shape == (4, 5)
        assert torch.all(probs >= 0)
        assert torch.allclose(probs.sum(dim=1), torch.ones(4), atol=1e-6)
    
    def test_advantage_network_output_shape(self):
        """AdvantageNetwork should output correct shape."""
        net = AdvantageNetwork(num_actions=5, backbone_type="mlp")
        x = torch.randn(4, 141)
        out = net(x)
        assert out.shape == (4, 5)
    
    def test_regret_matching(self):
        """RegretMatching should convert advantages to valid strategies."""
        rm = RegretMatching()
        
        # Test with positive advantages
        advantages = torch.tensor([[1.0, 2.0, 3.0, 0.0, -1.0]])
        strategy = rm(advantages)
        
        assert strategy.shape == (1, 5)
        assert torch.all(strategy >= 0)
        assert torch.allclose(strategy.sum(dim=1), torch.ones(1), atol=1e-6)
        
        # Positive advantages should get proportional weight
        assert strategy[0, 2] > strategy[0, 0]  # 3.0 > 1.0
    
    def test_regret_matching_all_negative(self):
        """RegretMatching should return uniform for all-negative advantages."""
        rm = RegretMatching()
        advantages = torch.tensor([[-1.0, -2.0, -3.0]])
        strategy = rm(advantages)
        
        # Should be approximately uniform
        uniform = torch.ones_like(strategy) / strategy.size(-1)
        assert torch.allclose(strategy, uniform, atol=1e-6)


class TestDeepCFRSolverIntegration:
    """Integration tests for Deep CFR solver (requires torch)."""
    
    @pytest.fixture
    def kuhn_game(self):
        """Create Kuhn game for testing."""
        from solver.games.kuhn import KuhnGame
        return KuhnGame()
    
    def test_solver_initialization(self, kuhn_game):
        """Solver should initialize without errors."""
        from solver.deep_cfr.solver import DeepCFRSolver, DeepCFRConfig
        
        config = DeepCFRConfig(
            num_iters=2,
            num_traversals=5,
            advantage_training_steps=2,
            strategy_training_steps=2,
            buffer_size=100,
        )
        solver = DeepCFRSolver(kuhn_game, config)
        
        assert solver.game == kuhn_game
        assert solver.max_actions >= 2
        assert len(solver.advantage_nets) == 2
    
    def test_solver_training_runs(self, kuhn_game):
        """Solver should complete training without errors."""
        from solver.deep_cfr.solver import DeepCFRSolver, DeepCFRConfig
        
        config = DeepCFRConfig(
            num_iters=3,
            num_traversals=10,
            advantage_training_steps=5,
            strategy_training_steps=5,
            buffer_size=500,
        )
        solver = DeepCFRSolver(kuhn_game, config)
        
        # Should not raise
        solver.train()
        
        # Check that buffers have data
        assert len(solver.advantage_buffers[0]) > 0
        assert len(solver.advantage_buffers[1]) > 0
    
    def test_solver_get_strategy(self, kuhn_game):
        """Solver should return valid strategy."""
        from solver.deep_cfr.solver import DeepCFRSolver, DeepCFRConfig
        from solver.games.kuhn import KuhnState
        
        config = DeepCFRConfig(
            num_iters=5,
            num_traversals=10,
            advantage_training_steps=5,
            strategy_training_steps=5,
            buffer_size=500,
        )
        solver = DeepCFRSolver(kuhn_game, config)
        solver.train()
        
        # Get strategy for a state
        state = KuhnState(cards=(2, 0), history="")  # King vs Jack
        strategy = solver.get_strategy(state)
        
        assert isinstance(strategy, dict)
        assert len(strategy) > 0
        
        # Probabilities should sum to ~1
        total = sum(strategy.values())
        assert abs(total - 1.0) < 0.1


class TestPostflopGame:
    """Tests for postflop game implementation."""
    
    @pytest.fixture
    def postflop_game(self):
        """Create postflop game for testing."""
        from solver.games.holdem import PostflopGame, BettingConfig
        config = BettingConfig(stack=100, pot=10)
        return PostflopGame(config)
    
    def test_initial_state(self, postflop_game):
        """Initial state should have correct properties."""
        state = postflop_game.initial_state()
        
        assert state.street == 0  # Flop
        assert len(state.full_board) == 5
        assert len(state.hu_state.board) == 3  # Flop cards
        assert state.hu_state.stacks[0] == 100
        assert state.hu_state.stacks[1] == 100
    
    def test_legal_actions(self, postflop_game):
        """Should return legal actions."""
        state = postflop_game.initial_state()
        actions = postflop_game.legal_actions(state)
        
        assert len(actions) > 0
        # Should have at least check and bet
        action_kinds = [a.kind for a in actions]
        assert any(k in action_kinds for k in [ActionKind.CHECK, ActionKind.FOLD])
    
    def test_terminal_fold(self, postflop_game):
        """Fold should create terminal state."""
        from engine.actions import Action, ActionKind
        
        state = postflop_game.initial_state()
        
        # Find fold action
        fold_action = None
        for action in postflop_game.legal_actions(state):
            if action.kind == ActionKind.FOLD:
                fold_action = action
                break
        
        if fold_action:
            new_state = postflop_game.apply(state, fold_action)
            assert postflop_game.is_terminal(new_state)
    
    def test_utility_fold(self, postflop_game):
        """Utility should work for fold scenarios."""
        from engine.actions import Action, ActionKind
        
        state = postflop_game.initial_state()
        
        # Find fold action
        fold_action = None
        for action in postflop_game.legal_actions(state):
            if action.kind == ActionKind.FOLD:
                fold_action = action
                break
        
        if fold_action:
            new_state = postflop_game.apply(state, fold_action)
            current = postflop_game.current_player(state)
            
            # Folder should lose committed chips
            utility = postflop_game.utility(new_state, current)
            assert utility <= 0  # Folder loses
            
            # Other player should win
            other = 1 - current
            utility_other = postflop_game.utility(new_state, other)
            assert utility_other >= 0
    
    def test_infoset_key(self, postflop_game):
        """Infoset key should be deterministic."""
        state = postflop_game.initial_state()
        
        key0 = postflop_game.infoset_key(state, 0)
        key1 = postflop_game.infoset_key(state, 1)
        
        assert isinstance(key0, str)
        assert isinstance(key1, str)
        assert key0 != key1  # Different players should have different keys
