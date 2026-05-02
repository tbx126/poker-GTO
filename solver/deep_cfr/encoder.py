"""Feature encoders for Deep CFR.

Implements two encoding strategies:
1. GameStateEncoder: flat feature vector (baseline)
2. GroupedTokenEncoder: semantic token groups for transformer (M3 target)

The GroupedTokenEncoder maps 141-dim raw features into 24 semantic tokens:
- CARD tokens: hole cards + board cards (up to 7)
- ROUND token: betting round info
- STATE token: stack/pot/committed info  
- ACT tokens: action history (up to 20 steps)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

import numpy as np
import torch
import torch.nn as nn


class TokenGroup(IntEnum):
    """Semantic token groups for the grouped-token transformer."""
    CARD = 0      # Card features (rank, suit, position)
    ROUND = 1     # Betting round
    STATE = 2     # Game state (stacks, pot, committed)
    ACT = 3       # Action history


@dataclass
class TokenSpec:
    """Specification for one token group."""
    group: TokenGroup
    dim: int          # Feature dimension per token
    max_count: int    # Max number of tokens in this group


# Token specifications matching the design guide
TOKEN_SPECS = [
    TokenSpec(TokenGroup.CARD, 8, 9),    # 2 hole + 5 board + 2 reserved
    TokenSpec(TokenGroup.ROUND, 4, 1),   # 1 round token
    TokenSpec(TokenGroup.STATE, 8, 1),   # 1 state token
    TokenSpec(TokenGroup.ACT, 6, 20),    # up to 20 action tokens
]

TOTAL_TOKENS = sum(s.max_count for s in TOKEN_SPECS)  # 31
TOKEN_DIM = 64  # Embedding dimension


class GameStateEncoder:
    """Encode HUState into flat feature vector for baseline MLP.
    
    Features (141 dims):
    - 52 card indicators (one-hot for each card)
    - 26 board cards (5 max, each 5-dim: rank_onehot_13 + suit_onehot_4)
    - 20 game state features
    - 43 action history features
    """
    
    RANK_CHARS = "23456789TJQKA"
    SUIT_CHARS = "hdcs"
    
    def encode_card(self, card_idx: int) -> np.ndarray:
        """Encode single card index to one-hot-like features."""
        if card_idx < 0 or card_idx > 51:
            return np.zeros(17)
        rank = card_idx // 4
        suit = card_idx % 4
        features = np.zeros(17)
        features[rank] = 1.0
        features[13 + suit] = 1.0
        return features
    
    def encode_state(self, state) -> np.ndarray:
        """Encode game state to 141-dim feature vector."""
        features = []
        
        # Hole cards (2 cards * 17 = 34 dims)
        for card in state.hole:
            for c in card:
                features.append(self.encode_card(c.mask.bit_length() - 1 if c.mask > 0 else -1))
        
        # Board cards (5 cards * 17 = 85 dims, padded to 5)
        board_cards = list(state.board)
        while len(board_cards) < 5:
            features.append(np.zeros(17))
            board_cards.append(None)
        for card in board_cards[:5]:
            if card is not None:
                features.append(self.encode_card(card.mask.bit_length() - 1 if card.mask > 0 else -1))
            else:
                features.append(np.zeros(17))
        
        # Game state features (22 dims)
        state_features = np.zeros(22)
        state_features[0] = state.stacks[0] / 200.0  # Normalized stack
        state_features[1] = state.stacks[1] / 200.0
        state_features[2] = state.pot / 200.0
        state_features[3] = state.committed[0] / 200.0
        state_features[4] = state.committed[1] / 200.0
        state_features[5] = state.to_act
        state_features[6] = state.last_raise_size / 100.0
        state_features[7] = len(state.board) / 5.0
        state_features[8] = 1.0 if state.folded is not None else 0.0
        if state.folded is not None:
            state_features[9] = state.folded
        features.append(state_features)
        
        return np.concatenate(features)


class GroupedTokenEncoder(nn.Module):
    """Grouped-Token Transformer encoder.
    
    Maps game state to sequence of semantic tokens for transformer processing.
    Each token group has its own linear projection.
    """
    
    def __init__(self, token_dim: int = TOKEN_DIM):
        super().__init__()
        self.token_dim = token_dim
        
        # Projections for each token group
        self.card_proj = nn.Linear(17, token_dim)
        self.round_proj = nn.Linear(4, token_dim)
        self.state_proj = nn.Linear(22, token_dim)
        self.act_proj = nn.Linear(10, token_dim)
        
        # Positional encoding for sequence
        self.pos_encoding = nn.Parameter(torch.randn(TOTAL_TOKENS, token_dim) * 0.02)
        
    def encode_card_token(self, card_features: torch.Tensor) -> torch.Tensor:
        """Encode card features to token embedding."""
        return self.card_proj(card_features)
    
    def encode_round_token(self, round_features: torch.Tensor) -> torch.Tensor:
        """Encode round info to token embedding."""
        return self.round_proj(round_features)
    
    def encode_state_token(self, state_features: torch.Tensor) -> torch.Tensor:
        """Encode state info to token embedding."""
        return self.state_proj(state_features)
    
    def encode_action_token(self, action_features: torch.Tensor) -> torch.Tensor:
        """Encode action history to token embedding."""
        return self.act_proj(action_features)
    
    def forward(self, card_tokens: torch.Tensor, round_token: torch.Tensor,
                state_token: torch.Tensor, act_tokens: torch.Tensor) -> torch.Tensor:
        """
        Args:
            card_tokens: (batch, 9, 17) - card features
            round_token: (batch, 1, 4) - round features
            state_token: (batch, 1, 22) - state features  
            act_tokens: (batch, 20, 10) - action features
            
        Returns:
            tokens: (batch, 31, token_dim) - encoded token sequence
        """
        batch_size = card_tokens.size(0)
        
        # Encode each group
        card_emb = self.card_proj(card_tokens)      # (B, 9, D)
        round_emb = self.round_proj(round_token)    # (B, 1, D)
        state_emb = self.state_proj(state_token)    # (B, 1, D)
        act_emb = self.act_proj(act_tokens)         # (B, 20, D)
        
        # Concatenate all tokens
        tokens = torch.cat([card_emb, round_emb, state_emb, act_emb], dim=1)  # (B, 31, D)
        
        # Add positional encoding
        tokens = tokens + self.pos_encoding.unsqueeze(0)
        
        return tokens


def extract_raw_features(state) -> dict:
    """Extract raw features from HUState for encoding.
    
    Returns dict with:
    - cards: list of card indices
    - round: betting round info
    - state: game state features
    - actions: action history features
    """
    features = {}
    
    # Card features
    cards = []
    for card_pair in state.hole:
        for card in card_pair:
            if card.mask > 0:
                cards.append(card.mask.bit_length() - 1)
            else:
                cards.append(-1)
    
    for card in state.board:
        if card.mask > 0:
            cards.append(card.mask.bit_length() - 1)
        else:
            cards.append(-1)
    
    features['cards'] = cards
    
    # Round features
    board_len = len(state.board)
    if board_len == 0:
        round_idx = 0  # preflop
    elif board_len == 3:
        round_idx = 1  # flop
    elif board_len == 4:
        round_idx = 2  # turn
    else:
        round_idx = 3  # river
    
    round_onehot = np.zeros(4)
    round_onehot[round_idx] = 1.0
    features['round'] = round_onehot
    
    # State features
    state_vec = np.zeros(22)
    state_vec[0] = state.stacks[0] / 200.0
    state_vec[1] = state.stacks[1] / 200.0
    state_vec[2] = state.pot / 200.0
    state_vec[3] = state.committed[0] / 200.0
    state_vec[4] = state.committed[1] / 200.0
    state_vec[5] = state.to_act
    state_vec[6] = state.last_raise_size / 100.0
    state_vec[7] = board_len / 5.0
    state_vec[8] = 1.0 if state.folded is not None else 0.0
    features['state'] = state_vec
    
    # Action history features
    actions = []
    for action in state.history[-20:]:  # Last 20 actions
        act_vec = np.zeros(10)
        act_vec[action.kind.value if hasattr(action.kind, 'value') else 0] = 1.0
        if action.amount is not None:
            act_vec[5] = action.amount / 200.0
        actions.append(act_vec)
    
    # Pad to 20 actions
    while len(actions) < 20:
        actions.append(np.zeros(10))
    
    features['actions'] = np.array(actions)
    
    return features
