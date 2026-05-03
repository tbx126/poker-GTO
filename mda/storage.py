"""Hand history storage with efficient querying.

Provides storage and indexing for hand histories with support for:
- Fast player-based queries
- Situation-based filtering
- Statistical aggregation
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from mda.parser import HandHistory, Street, Action


class HandHistoryStore:
    """Storage for hand histories using SQLite.
    
    Supports efficient querying by:
    - Player name
    - Hand ID
    - Date range
    - Stack depth
    - Position
    """
    
    def __init__(self, db_path: str = ":memory:"):
        """Initialize store.
        
        Args:
            db_path: Path to SQLite database, or ":memory:" for in-memory
        """
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
    
    def _create_tables(self):
        """Create database tables."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hands (
                hand_id TEXT PRIMARY KEY,
                timestamp TEXT,
                table_name TEXT,
                max_seats INTEGER,
                button_seat INTEGER,
                small_blind REAL,
                big_blind REAL,
                pot REAL,
                rake REAL,
                board TEXT,
                raw_text TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hand_id TEXT,
                player_name TEXT,
                starting_stack REAL,
                position TEXT,
                FOREIGN KEY (hand_id) REFERENCES hands(hand_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hand_id TEXT,
                player_name TEXT,
                street TEXT,
                action_type TEXT,
                amount REAL,
                sequence_order INTEGER,
                FOREIGN KEY (hand_id) REFERENCES hands(hand_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS winners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hand_id TEXT,
                player_name TEXT,
                amount REAL,
                FOREIGN KEY (hand_id) REFERENCES hands(hand_id)
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_players_name ON players(player_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_player ON actions(player_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_hand ON actions(hand_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hands_timestamp ON hands(timestamp)")
        
        self.conn.commit()
    
    def add_hand(self, hand: HandHistory):
        """Add a hand history to the store."""
        cursor = self.conn.cursor()
        
        # Insert hand
        cursor.execute("""
            INSERT OR REPLACE INTO hands 
            (hand_id, timestamp, table_name, max_seats, button_seat, 
             small_blind, big_blind, pot, rake, board, raw_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            hand.hand_id,
            hand.timestamp.isoformat(),
            hand.table_name,
            hand.max_seats,
            hand.button_seat,
            hand.blinds[0],
            hand.blinds[1],
            hand.pot,
            hand.rake,
            json.dumps(hand.board),
            hand.raw_text,
        ))
        
        # Insert players
        for name, stack in hand.players.items():
            # Determine position relative to button
            cursor.execute("""
                INSERT INTO players (hand_id, player_name, starting_stack, position)
                VALUES (?, ?, ?, ?)
            """, (hand.hand_id, name, stack, "unknown"))
        
        # Insert actions
        for i, action in enumerate(hand.actions):
            cursor.execute("""
                INSERT INTO actions (hand_id, player_name, street, action_type, amount, sequence_order)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                hand.hand_id,
                action.player,
                action.street.value,
                action.action.value,
                action.amount,
                i,
            ))
        
        # Insert winners
        for name, amount in hand.winners.items():
            cursor.execute("""
                INSERT INTO winners (hand_id, player_name, amount)
                VALUES (?, ?, ?)
            """, (hand.hand_id, name, amount))
        
        self.conn.commit()
    
    def add_hands(self, hands: list[HandHistory]):
        """Add multiple hand histories."""
        for hand in hands:
            self.add_hand(hand)
    
    def get_hand(self, hand_id: str) -> Optional[HandHistory]:
        """Get a hand by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM hands WHERE hand_id = ?", (hand_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        # Reconstruct HandHistory (simplified)
        return HandHistory(
            hand_id=row["hand_id"],
            timestamp=row["timestamp"],
            table_name=row["table_name"],
            max_seats=row["max_seats"],
            button_seat=row["button_seat"],
            blinds=(row["small_blind"], row["big_blind"]),
            players={},
            pot=row["pot"],
            rake=row["rake"],
            board=json.loads(row["board"]),
            raw_text=row["raw_text"],
        )
    
    def get_player_hands(self, player_name: str, limit: int = 100) -> list[str]:
        """Get hand IDs for a specific player."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT hand_id FROM players 
            WHERE player_name = ? 
            ORDER BY hand_id DESC 
            LIMIT ?
        """, (player_name, limit))
        
        return [row["hand_id"] for row in cursor.fetchall()]
    
    def get_player_actions(self, player_name: str, street: Optional[Street] = None) -> list[dict]:
        """Get all actions for a player."""
        cursor = self.conn.cursor()
        
        if street:
            cursor.execute("""
                SELECT * FROM actions 
                WHERE player_name = ? AND street = ?
                ORDER BY sequence_order
            """, (player_name, street.value))
        else:
            cursor.execute("""
                SELECT * FROM actions 
                WHERE player_name = ?
                ORDER BY hand_id, sequence_order
            """, (player_name,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_player_stats(self, player_name: str) -> dict:
        """Get basic statistics for a player."""
        cursor = self.conn.cursor()
        
        # Total hands played
        cursor.execute("""
            SELECT COUNT(DISTINCT hand_id) as total_hands
            FROM players WHERE player_name = ?
        """, (player_name,))
        total_hands = cursor.fetchone()["total_hands"]
        
        # VPIP (Voluntarily Put money In Pot)
        cursor.execute("""
            SELECT COUNT(DISTINCT a.hand_id) as vpip_hands
            FROM actions a
            WHERE a.player_name = ? 
            AND a.street = 'preflop'
            AND a.action_type IN ('call', 'raise', 'bet', 'all_in')
        """, (player_name,))
        vpip_hands = cursor.fetchone()["vpip_hands"]
        
        # PFR (Pre-Flop Raise)
        cursor.execute("""
            SELECT COUNT(DISTINCT a.hand_id) as pfr_hands
            FROM actions a
            WHERE a.player_name = ? 
            AND a.street = 'preflop'
            AND a.action_type IN ('raise', 'bet', 'all_in')
        """, (player_name,))
        pfr_hands = cursor.fetchone()["pfr_hands"]
        
        # Aggression Factor
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN action_type IN ('bet', 'raise') THEN 1 ELSE 0 END) as aggressive,
                SUM(CASE WHEN action_type = 'call' THEN 1 ELSE 0 END) as passive
            FROM actions
            WHERE player_name = ?
        """, (player_name,))
        agg_row = cursor.fetchone()
        aggressive = agg_row["aggressive"] or 0
        passive = agg_row["passive"] or 1
        af = aggressive / passive if passive > 0 else 0
        
        # Win rate
        cursor.execute("""
            SELECT COUNT(*) as wins FROM winners WHERE player_name = ?
        """, (player_name,))
        wins = cursor.fetchone()["wins"]
        
        return {
            "total_hands": total_hands,
            "vpip": vpip_hands / total_hands if total_hands > 0 else 0,
            "pfr": pfr_hands / total_hands if total_hands > 0 else 0,
            "aggression_factor": af,
            "win_rate": wins / total_hands if total_hands > 0 else 0,
            "total_wins": wins,
        }
    
    def get_population_stats(self, min_hands: int = 10) -> dict:
        """Get population-level statistics."""
        cursor = self.conn.cursor()
        
        # Get players with enough hands
        cursor.execute("""
            SELECT player_name, COUNT(DISTINCT hand_id) as hand_count
            FROM players
            GROUP BY player_name
            HAVING hand_count >= ?
        """, (min_hands,))
        
        players = cursor.fetchall()
        stats = []
        
        for player_row in players:
            player_stats = self.get_player_stats(player_row["player_name"])
            player_stats["player_name"] = player_row["player_name"]
            stats.append(player_stats)
        
        if not stats:
            return {"players": 0, "avg_vpip": 0, "avg_pfr": 0, "avg_af": 0}
        
        return {
            "players": len(stats),
            "avg_vpip": sum(s["vpip"] for s in stats) / len(stats),
            "avg_pfr": sum(s["pfr"] for s in stats) / len(stats),
            "avg_af": sum(s["aggression_factor"] for s in stats) / len(stats),
            "players": stats,
        }
    
    def get_situation_stats(self, situation: str) -> dict:
        """Get statistics for a specific situation.
        
        Args:
            situation: Situation string like "BTN_vs_BB_open" or "BB_defend_vs_BTN"
        """
        # This is a simplified implementation
        # In production, would parse situation and query accordingly
        cursor = self.conn.cursor()
        
        # Example: Get BB defend rate vs open
        cursor.execute("""
            SELECT 
                a.player_name,
                COUNT(DISTINCT a.hand_id) as hands,
                SUM(CASE WHEN a.action_type = 'fold' THEN 1 ELSE 0 END) as folds,
                SUM(CASE WHEN a.action_type = 'call' THEN 1 ELSE 0 END) as calls,
                SUM(CASE WHEN a.action_type IN ('raise', 'bet', '3bet') THEN 1 ELSE 0 END) as raises
            FROM actions a
            WHERE a.street = 'preflop'
            AND a.action_type IN ('fold', 'call', 'raise')
            GROUP BY a.player_name
        """)
        
        return {"situation": situation, "data": [dict(row) for row in cursor.fetchall()]}
    
    def close(self):
        """Close the database connection."""
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
