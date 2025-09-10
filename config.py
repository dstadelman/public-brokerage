"""
Configuration management for the Public Brokerage Shell.
Handles persistent settings, default account, and user preferences.
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Config:
    """Configuration manager for persistent shell settings."""
    
    def __init__(self):
        self.config_dir = Path.home() / '.public_brokerage'
        self.config_file = self.config_dir / 'config.json'
        self.config_data: Dict[str, Any] = {}
        self._ensure_config_dir()
        self.load()
    
    def _ensure_config_dir(self) -> None:
        """Ensure configuration directory exists."""
        try:
            self.config_dir.mkdir(exist_ok=True, parents=True)
        except Exception as e:
            logger.warning(f"Could not create config directory: {e}")
    
    def load(self) -> None:
        """Load configuration from file."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    self.config_data = json.load(f)
                logger.debug(f"Loaded config from {self.config_file}")
            else:
                self.config_data = self._get_default_config()
                self.save()
                logger.info(f"Created new config file at {self.config_file}")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.config_data = self._get_default_config()
    
    def save(self) -> None:
        """Save configuration to file."""
        try:
            self.config_data['last_updated'] = datetime.now().isoformat()
            with open(self.config_file, 'w') as f:
                json.dump(self.config_data, f, indent=2)
            logger.debug(f"Saved config to {self.config_file}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values."""
        return {
            'default_account_id': None,
            'max_wait_time': 42,
            'use_colors': True,
            'auto_save_history': True,
            'command_history_size': 1000,
            'background_processes': {},
            'last_updated': datetime.now().isoformat(),
            'version': '1.0.0'
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config_data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value and save."""
        self.config_data[key] = value
        self.save()
    
    def get_default_account(self) -> Optional[str]:
        """Get the default account ID."""
        return self.get('default_account_id')
    
    def set_default_account(self, account_id: str) -> None:
        """Set the default account ID."""
        self.set('default_account_id', account_id)
        logger.info(f"Set default account to: {account_id}")
    
    def get_max_wait_time(self) -> int:
        """Get default max wait time for orders."""
        return self.get('max_wait_time', 42)
    
    def set_max_wait_time(self, seconds: int) -> None:
        """Set default max wait time for orders."""
        self.set('max_wait_time', seconds)
    
    def use_colors(self) -> bool:
        """Check if colored output is enabled."""
        return self.get('use_colors', True)
    
    def add_background_process(self, process_id: str, process_info: Dict[str, Any]) -> None:
        """Add a background process to config."""
        processes = self.get('background_processes', {})
        processes[process_id] = process_info
        self.set('background_processes', processes)
    
    def remove_background_process(self, process_id: str) -> None:
        """Remove a background process from config."""
        processes = self.get('background_processes', {})
        if process_id in processes:
            del processes[process_id]
            self.set('background_processes', processes)
    
    def get_background_processes(self) -> Dict[str, Any]:
        """Get all background processes."""
        return self.get('background_processes', {})
    
    def clear_background_processes(self) -> None:
        """Clear all background processes."""
        self.set('background_processes', {})


# Global config instance
config = Config()
