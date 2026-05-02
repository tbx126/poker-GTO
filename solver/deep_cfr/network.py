"""Neural networks for Deep CFR.

Implements:
1. ValueNetwork: estimates counterfactual values for each player
2. StrategyNetwork: outputs action probabilities

Both networks support two modes:
- MLP mode: flat feature input (baseline)
- Transformer mode: grouped-token input (M3 target)
"""

from __future__ import annotations

from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from solver.deep_cfr.encoder import TOKEN_DIM, TOTAL_TOKENS


class MLPBackbone(nn.Module):
    """MLP backbone for flat feature encoding."""
    
    def __init__(self, input_dim: int = 141, hidden_dims: list[int] = None):
        super().__init__()
        if hidden_dims is None:
            hidden_dims = [256, 256, 128]
        
        layers = []
        prev_dim = input_dim
        for dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, dim),
                nn.LayerNorm(dim),
                nn.ReLU(),
                nn.Dropout(0.1),
            ])
            prev_dim = dim
        
        self.net = nn.Sequential(*layers)
        self.output_dim = hidden_dims[-1]
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class TransformerBackbone(nn.Module):
    """Transformer backbone for grouped-token encoding."""
    
    def __init__(self, token_dim: int = TOKEN_DIM, num_heads: int = 4, 
                 num_layers: int = 3, ff_dim: int = 256):
        super().__init__()
        
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=token_dim,
            nhead=num_heads,
            dim_feedforward=ff_dim,
            dropout=0.1,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.output_dim = token_dim
    
    def forward(self, tokens: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        """
        Args:
            tokens: (batch, seq_len, token_dim)
            mask: optional attention mask
            
        Returns:
            pooled: (batch, token_dim) - mean-pooled output
        """
        # Transformer encoding
        encoded = self.transformer(tokens, src_key_padding_mask=mask)  # (B, S, D)
        
        # Mean pooling over sequence
        pooled = encoded.mean(dim=1)  # (B, D)
        
        return pooled


class ValueNetwork(nn.Module):
    """Counterfactual value network.
    
    Estimates V(I, a) for each infoset I and action a.
    Used to replace the regret table in tabular CFR.
    """
    
    def __init__(self, num_actions: int = 5, backbone_type: str = "mlp",
                 token_dim: int = TOKEN_DIM):
        super().__init__()
        self.num_actions = num_actions
        
        if backbone_type == "mlp":
            self.backbone = MLPBackbone(input_dim=141)
        else:
            self.backbone = TransformerBackbone(token_dim=token_dim)
        
        # Value heads for each action
        self.value_head = nn.Sequential(
            nn.Linear(self.backbone.output_dim, 128),
            nn.ReLU(),
            nn.Linear(128, num_actions),
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, input_dim) for MLP or (batch, seq_len, token_dim) for transformer
            
        Returns:
            values: (batch, num_actions) - counterfactual values
        """
        features = self.backbone(x)
        return self.value_head(features)


class StrategyNetwork(nn.Module):
    """Strategy network.
    
    Outputs action probabilities conditioned on the infoset.
    Used to replace the strategy table in tabular CFR.
    """
    
    def __init__(self, num_actions: int = 5, backbone_type: str = "mlp",
                 token_dim: int = TOKEN_DIM):
        super().__init__()
        self.num_actions = num_actions
        
        if backbone_type == "mlp":
            self.backbone = MLPBackbone(input_dim=141)
        else:
            self.backbone = TransformerBackbone(token_dim=token_dim)
        
        # Strategy head with softmax
        self.strategy_head = nn.Sequential(
            nn.Linear(self.backbone.output_dim, 128),
            nn.ReLU(),
            nn.Linear(128, num_actions),
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, input_dim) for MLP or (batch, seq_len, token_dim) for transformer
            
        Returns:
            probs: (batch, num_actions) - action probabilities (sum to 1)
        """
        features = self.backbone(x)
        logits = self.strategy_head(features)
        return F.softmax(logits, dim=-1)


class AdvantageNetwork(nn.Module):
    """Advantage network for Deep CFR.
    
    Estimates A(I, a) = Q(I, a) - V(I) for each infoset.
    This is the "regret" in counterfactual regret minimization.
    """
    
    def __init__(self, num_actions: int = 5, backbone_type: str = "mlp",
                 token_dim: int = TOKEN_DIM):
        super().__init__()
        self.num_actions = num_actions
        
        if backbone_type == "mlp":
            self.backbone = MLPBackbone(input_dim=141)
        else:
            self.backbone = TransformerBackbone(token_dim=token_dim)
        
        # Advantage head (no activation - can be negative)
        self.advantage_head = nn.Sequential(
            nn.Linear(self.backbone.output_dim, 128),
            nn.ReLU(),
            nn.Linear(128, num_actions),
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: input features
            
        Returns:
            advantages: (batch, num_actions) - action advantages
        """
        features = self.backbone(x)
        return self.advantage_head(features)


class RegretMatching(nn.Module):
    """Regret matching layer.
    
    Converts advantages to strategy using regret matching:
    sigma(a) = max(advantage(a), 0) / sum(max(advantage(a'), 0))
    
    If all advantages <= 0, returns uniform distribution.
    """
    
    def __init__(self, eps: float = 1e-8):
        super().__init__()
        self.eps = eps
    
    def forward(self, advantages: torch.Tensor) -> torch.Tensor:
        """
        Args:
            advantages: (batch, num_actions)
            
        Returns:
            strategy: (batch, num_actions) - probabilities summing to 1
        """
        # ReLU on advantages (positive regret only)
        positive = F.relu(advantages)
        
        # Sum over actions
        total = positive.sum(dim=-1, keepdim=True)
        
        # Normalize, with uniform fallback
        uniform = torch.ones_like(advantages) / advantages.size(-1)
        strategy = torch.where(
            total > self.eps,
            positive / (total + self.eps),
            uniform,
        )
        
        return strategy
