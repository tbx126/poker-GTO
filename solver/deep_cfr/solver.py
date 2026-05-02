"""Deep CFR solver.

Implements Deep Counterfactual Regret Minimization using neural networks
to estimate counterfactual values, replacing the tabular regret/strategy
stores in classical CFR+.

Key improvements over tabular CFR:
1. Generalization across similar infosets
2. No explicit abstraction needed
3. Scales to larger game trees (postflop)

Reference: "Deep Counterfactual Regret Minimization" (Brown et al., 2019)
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Hashable, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from solver.deep_cfr.network import (
    AdvantageNetwork,
    RegretMatching,
    StrategyNetwork,
    ValueNetwork,
)
from solver.games.base import Game


@dataclass
class DeepCFRConfig:
    """Configuration for Deep CFR solver."""
    
    # Network architecture
    backbone_type: str = "mlp"  # "mlp" or "transformer"
    hidden_dims: list[int] = field(default_factory=lambda: [256, 256, 128])
    
    # Training
    num_iters: int = 1000
    batch_size: int = 256
    learning_rate: float = 1e-3
    buffer_size: int = 100_000
    
    # Deep CFR specific
    num_traversals: int = 100  # Tree traversals per iteration
    advantage_training_steps: int = 100
    strategy_training_steps: int = 50
    
    # Device
    device: str = "cpu"


@dataclass
class ExperienceBuffer:
    """Experience buffer for Deep CFR training.
    
    Stores (infoset_features, player, action_utilities, reach_prob) tuples.
    """
    
    features: list[np.ndarray] = field(default_factory=list)
    players: list[int] = field(default_factory=list)
    utilities: list[np.ndarray] = field(default_factory=list)
    reach_probs: list[float] = field(default_factory=list)
    
    max_size: int = 100_000
    
    def add(self, features: np.ndarray, player: int, 
            utilities: np.ndarray, reach: float):
        """Add experience to buffer."""
        if len(self.features) >= self.max_size:
            # Replace oldest
            idx = len(self.features) % self.max_size
            self.features[idx] = features
            self.players[idx] = player
            self.utilities[idx] = utilities
            self.reach_probs[idx] = reach
        else:
            self.features.append(features)
            self.players.append(player)
            self.utilities.append(utilities)
            self.reach_probs.append(reach)
    
    def sample(self, batch_size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Sample random batch from buffer."""
        n = len(self.features)
        if n == 0:
            raise ValueError("Buffer is empty")
        
        indices = np.random.choice(n, min(batch_size, n), replace=False)
        
        features = np.stack([self.features[i] for i in indices])
        players = np.array([self.players[i] for i in indices])
        utilities = np.stack([self.utilities[i] for i in indices])
        reach = np.array([self.reach_probs[i] for i in indices])
        
        return features, players, utilities, reach
    
    def __len__(self):
        return len(self.features)


class DeepCFRSolver:
    """Deep CFR solver using neural networks.
    
    Replaces tabular regret/strategy storage with neural network
    function approximation. Supports both MLP and Transformer backbones.
    
    Usage:
        solver = DeepCFRSolver(game, config)
        solver.train()  # Train networks
        strategy = solver.get_strategy(state)  # Get Nash strategy
    """
    
    def __init__(self, game: Game, config: Optional[DeepCFRConfig] = None):
        self.game = game
        self.config = config or DeepCFRConfig()
        
        self.device = torch.device(self.config.device)
        
        # Get max actions from game
        self.max_actions = self._get_max_actions()
        
        # Initialize networks
        self.advantage_nets = {
            p: AdvantageNetwork(
                num_actions=self.max_actions,
                backbone_type=self.config.backbone_type,
            ).to(self.device)
            for p in range(game.num_players)
        }
        
        self.strategy_net = StrategyNetwork(
            num_actions=self.max_actions,
            backbone_type=self.config.backbone_type,
        ).to(self.device)
        
        # Regret matching layer
        self.regret_matching = RegretMatching()
        
        # Experience buffers
        self.advantage_buffers = {
            p: ExperienceBuffer(max_size=self.config.buffer_size)
            for p in range(game.num_players)
        }
        self.strategy_buffer = ExperienceBuffer(max_size=self.config.buffer_size)
        
        # Optimizers
        self.advantage_optimizers = {
            p: optim.Adam(self.advantage_nets[p].parameters(), lr=self.config.learning_rate)
            for p in range(game.num_players)
        }
        self.strategy_optimizer = optim.Adam(
            self.strategy_net.parameters(), lr=self.config.learning_rate
        )
        
        # Training stats
        self.iter = 0
        self.advantage_losses = defaultdict(list)
        self.strategy_losses = []
    
    def _get_max_actions(self) -> int:
        """Get maximum number of legal actions across all states."""
        # Sample some states to estimate
        max_actions = 0
        for _ in range(100):
            state = self.game.initial_state()
            while not self.game.is_terminal(state):
                if self.game.is_chance(state):
                    outcomes = self.game.chance_outcomes(state)
                    if outcomes:
                        state = self.game.apply_chance(state, outcomes[0][0])
                    continue
                
                actions = self.game.legal_actions(state)
                max_actions = max(max_actions, len(actions))
                
                # Take first action
                if actions:
                    state = self.game.apply(state, actions[0])
                else:
                    break
        
        return max(max_actions, 2)  # At least 2 actions
    
    def _state_to_features(self, state) -> np.ndarray:
        """Convert game state to feature vector for neural network."""
        # Simple feature encoding - can be enhanced with GroupedTokenEncoder
        features = []
        
        # Encode based on game type
        if hasattr(state, 'cards') and state.cards is not None:
            # Kuhn/Leduc style
            for card in state.cards:
                card_onehot = np.zeros(3)
                card_onehot[card] = 1.0
                features.append(card_onehot)
        elif hasattr(state, 'hole'):
            # HU postflop style
            for card_pair in state.hole:
                for card in card_pair:
                    features.append(np.array([card.rank / 13.0, card.suit / 4.0]))
            for card in state.board:
                features.append(np.array([card.rank / 13.0, card.suit / 4.0]))
        
        # Pad or truncate to fixed size
        while len(features) < 10:
            features.append(np.zeros(features[0].shape if features else 2))
        features = features[:10]
        
        # Flatten
        flat = np.concatenate(features)
        
        # Pad to 141 dims
        if len(flat) < 141:
            flat = np.pad(flat, (0, 141 - len(flat)))
        
        return flat[:141].astype(np.float32)
    
    def _get_strategy(self, features: np.ndarray) -> np.ndarray:
        """Get strategy from strategy network."""
        with torch.no_grad():
            x = torch.tensor(features, dtype=torch.float32, device=self.device).unsqueeze(0)
            probs = self.strategy_net(x).squeeze(0).cpu().numpy()
        return probs
    
    def _traverse(self, state, player: int, reach: list[float]) -> float:
        """Tree traversal for one player, collecting advantage training data.
        
        Returns counterfactual value for the traversing player.
        """
        if self.game.is_terminal(state):
            return self.game.utility(state, player)
        
        if self.game.is_chance(state):
            ev = 0.0
            for outcome, prob in self.game.chance_outcomes(state):
                new_reach = reach.copy()
                for p in range(self.game.num_players):
                    if p != player:
                        new_reach[p] *= prob
                ev += prob * self._traverse(
                    self.game.apply_chance(state, outcome), player, new_reach
                )
            return ev
        
        current = self.game.current_player(state)
        actions = self.game.legal_actions(state)
        n_actions = len(actions)
        
        # Get features for this infoset
        features = self._state_to_features(state)
        
        # Get current strategy from network
        strategy = self._get_strategy(features)[:n_actions]
        strategy = strategy / (strategy.sum() + 1e-8)  # Normalize
        
        # Recurse for each action
        action_values = np.zeros(n_actions)
        for i, action in enumerate(actions):
            new_reach = reach.copy()
            new_reach[current] *= strategy[i]
            action_values[i] = self._traverse(
                self.game.apply(state, action), player, new_reach
            )
        
        # Node value
        node_value = np.dot(strategy, action_values)
        
        # If current player is the traverser, compute counterfactual values
        if current == player:
            # Counterfactual values weighted by opponent reach
            opp_reach = 1.0
            for p in range(self.game.num_players):
                if p != current:
                    opp_reach *= reach[p]
            
            # Advantage = action_value - node_value
            advantages = opp_reach * (action_values - node_value)
            
            # Store in buffer
            self.advantage_buffers[player].add(
                features, current, advantages, reach[current]
            )
        
        return node_value
    
    def _train_advantage_networks(self):
        """Train advantage networks on collected data."""
        for player in range(self.game.num_players):
            buffer = self.advantage_buffers[player]
            if len(buffer) == 0:
                continue
            
            net = self.advantage_nets[player]
            optimizer = self.advantage_optimizers[player]
            
            net.train()
            total_loss = 0.0
            steps = 0
            
            for _ in range(self.config.advantage_training_steps):
                if len(buffer) < self.config.batch_size:
                    break
                
                features, players, advantages, reach = buffer.sample(self.config.batch_size)
                
                x = torch.tensor(features, dtype=torch.float32, device=self.device)
                target = torch.tensor(advantages, dtype=torch.float32, device=self.device)
                weights = torch.tensor(reach, dtype=torch.float32, device=self.device)
                
                # Forward
                pred = net(x)
                
                # Weighted MSE loss
                loss = (weights.unsqueeze(1) * (pred - target) ** 2).mean()
                
                # Backward
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                
                total_loss += loss.item()
                steps += 1
            
            if steps > 0:
                self.advantage_losses[player].append(total_loss / steps)
    
    def _train_strategy_network(self):
        """Train strategy network using advantage-weighted regression."""
        # Collect strategy training data from all players
        all_features = []
        all_target_strategies = []
        
        for player in range(self.game.num_players):
            buffer = self.advantage_buffers[player]
            if len(buffer) == 0:
                continue
            
            features, _, advantages, _ = buffer.sample(min(len(buffer), 1000))
            
            # Convert advantages to target strategies via regret matching
            with torch.no_grad():
                adv_tensor = torch.tensor(advantages, dtype=torch.float32)
                target_strategy = self.regret_matching(adv_tensor).numpy()
            
            all_features.append(features)
            all_target_strategies.append(target_strategy)
        
        if not all_features:
            return
        
        features = np.concatenate(all_features)
        target = np.concatenate(all_target_strategies)
        
        # Train strategy network
        self.strategy_net.train()
        total_loss = 0.0
        steps = 0
        
        for _ in range(self.config.strategy_training_steps):
            indices = np.random.choice(len(features), min(self.config.batch_size, len(features)))
            
            x = torch.tensor(features[indices], dtype=torch.float32, device=self.device)
            y = torch.tensor(target[indices], dtype=torch.float32, device=self.device)
            
            pred = self.strategy_net(x)
            loss = -(y * torch.log(pred + 1e-8)).sum(dim=1).mean()
            
            self.strategy_optimizer.zero_grad()
            loss.backward()
            self.strategy_optimizer.step()
            
            total_loss += loss.item()
            steps += 1
        
        if steps > 0:
            self.strategy_losses.append(total_loss / steps)
    
    def train(self, num_iters: Optional[int] = None):
        """Run Deep CFR training.
        
        Args:
            num_iters: Number of training iterations (overrides config)
        """
        iters = num_iters or self.config.num_iters
        
        print(f"Starting Deep CFR training for {iters} iterations...")
        print(f"Game: {self.game.__class__.__name__}")
        print(f"Players: {self.game.num_players}")
        print(f"Max actions: {self.max_actions}")
        print(f"Device: {self.device}")
        print()
        
        started = time.perf_counter()
        
        for i in range(iters):
            self.iter += 1
            
            # Tree traversals to collect data
            for _ in range(self.config.num_traversals):
                for player in range(self.game.num_players):
                    state = self.game.initial_state()
                    reach = [1.0] * self.game.num_players
                    self._traverse(state, player, reach)
            
            # Train networks
            self._train_advantage_networks()
            self._train_strategy_network()
            
            # Progress reporting
            if (i + 1) % 10 == 0 or i == 0:
                elapsed = time.perf_counter() - started
                avg_adv_loss = np.mean([
                    losses[-1] if losses else 0 
                    for losses in self.advantage_losses.values()
                ])
                avg_strat_loss = self.strategy_losses[-1] if self.strategy_losses else 0
                
                print(
                    f"Iter {i+1}/{iters} | "
                    f"Adv Loss: {avg_adv_loss:.4f} | "
                    f"Strat Loss: {avg_strat_loss:.4f} | "
                    f"Buffer: {len(self.advantage_buffers[0])} | "
                    f"Time: {elapsed:.1f}s"
                )
        
        total_time = time.perf_counter() - started
        print(f"\nTraining complete in {total_time:.1f}s")
    
    def get_strategy(self, state) -> dict[int, float]:
        """Get Nash strategy for a given state.
        
        Returns:
            Dict mapping action index to probability
        """
        features = self._state_to_features(state)
        actions = self.game.legal_actions(state)
        
        probs = self._get_strategy(features)[:len(actions)]
        probs = probs / (probs.sum() + 1e-8)  # Normalize
        
        return {action: float(prob) for action, prob in zip(actions, probs)}
    
    def get_average_strategy(self) -> dict[Hashable, np.ndarray]:
        """Get average strategy across all visited infosets.
        
        For compatibility with tabular CFR interface.
        """
        # This is a simplified version - in practice would need
        # to track all visited infosets
        return {}
    
    def exploitability(self) -> float:
        """Compute exploitability of current strategy.
        
        Returns sum of best response values for each player.
        """
        # Simplified - compute on sampled states
        total_br_value = 0.0
        
        for player in range(self.game.num_players):
            br_value = self._compute_best_response(player)
            total_br_value += abs(br_value)
        
        return total_br_value
    
    def _compute_best_response(self, br_player: int) -> float:
        """Compute best response value for a player."""
        def walk(state, opp_reach: float) -> float:
            if self.game.is_terminal(state):
                return self.game.utility(state, br_player) * opp_reach
            
            if self.game.is_chance(state):
                ev = 0.0
                for outcome, prob in self.game.chance_outcomes(state):
                    ev += walk(self.game.apply_chance(state, outcome), opp_reach * prob)
                return ev
            
            current = self.game.current_player(state)
            actions = self.game.legal_actions(state)
            
            if current == br_player:
                # Maximize over actions
                best_value = float('-inf')
                for action in actions:
                    value = walk(self.game.apply(state, action), opp_reach)
                    best_value = max(best_value, value)
                return best_value
            else:
                # Use current strategy
                features = self._state_to_features(state)
                strategy = self._get_strategy(features)[:len(actions)]
                strategy = strategy / (strategy.sum() + 1e-8)
                
                ev = 0.0
                for i, action in enumerate(actions):
                    ev += strategy[i] * walk(
                        self.game.apply(state, action), opp_reach * strategy[i]
                    )
                return ev
        
        return walk(self.game.initial_state(), 1.0)
