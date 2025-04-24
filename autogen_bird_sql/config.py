"""
Configuration module for BirdSQLOrchestrator.

This module provides configuration helpers for the BirdSQLOrchestrator and its agents.
It includes functions to load configurations from different sources and set up LLM configs.
"""

import os
import json
import yaml
from typing import Dict, List, Any, Optional

# Default configuration values
DEFAULT_CONFIG = {
    "llm": {
        "provider": "anthropic",
        "model": "claude-3-7-sonnet-20250219",
        "temperature": 0.0,
        "max_tokens": 1000,
        "top_p": 1.0,
        "timeout": 120
    },
    "database": {
        "path": "./data/databases"
    },
    "agents": {
        "max_repair_attempts": 3,
        "max_consecutive_replies": 10
    },
    "debug_mode": False
}

def load_config_from_file(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from a file (JSON or YAML).
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Loaded configuration dictionary
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        if config_path.endswith('.json'):
            return json.load(f)
        elif config_path.endswith('.yaml') or config_path.endswith('.yml'):
            import yaml
            return yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported configuration file format: {config_path}")

def get_llm_config(config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Get a simplified LLM configuration for agents.
    
    This function creates a basic configuration dictionary suitable for use with Autogen agents.
    
    Args:
        config: Optional configuration dictionary to use
        
    Returns:
        LLM configuration dictionary for Autogen agents
    """
    # Set up for Anthropic Claude by default
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    model = "claude-3-7-sonnet-20250219"  # Default to Claude 3.7
    provider = "anthropic"
    
    # Update with provided config if available
    if config and "llm" in config:
        if "model" in config["llm"]:
            model = config["llm"]["model"]
        if "provider" in config["llm"]:
            provider = config["llm"]["provider"]
    
    if provider == "anthropic":
        config_list = [{"model": model, "api_key": api_key}]
    else:
        # Fallback for other providers like OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "")
        config_list = [{"model": model, "api_key": api_key}]
    
    return {"config_list": config_list}

def get_database_config(config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Get the database configuration.
    
    Args:
        config: Optional configuration dictionary to use
        
    Returns:
        Database configuration dictionary
    """
    # Start with default configuration
    db_config = DEFAULT_CONFIG["database"].copy()
    
    # Update with provided config if available
    if config and "database" in config:
        db_config.update(config["database"])
    
    # Update with environment variables if available
    if os.environ.get("BIRD_SQL_DB_PATH"):
        db_config["path"] = os.environ.get("BIRD_SQL_DB_PATH")
    
    return db_config

def create_agent_configs(config: Dict[str, Any] = None) -> Dict[str, Dict[str, Any]]:
    """
    Create agent-specific configurations.
    
    Args:
        config: Optional configuration dictionary to use
        
    Returns:
        Dictionary with configurations for each agent type
    """
    # Get the base LLM config all agents will use
    llm_config = get_llm_config(config)
    
    # Start with default agent settings
    agent_config = DEFAULT_CONFIG["agents"].copy()
    
    # Update with provided config if available
    if config and "agents" in config:
        agent_config.update(config["agents"])
    
    # Create agent-specific configurations
    agent_configs = {
        "interpreter": {
            "llm_config": llm_config,
        },
        "schema": {
            "llm_config": llm_config,
        },
        "generator": {
            "llm_config": llm_config,
        },
        "executor": {
            "llm_config": llm_config,
        },
        "validator": {
            "llm_config": llm_config,
        },
        "repair": {
            "llm_config": llm_config,
            "max_repair_attempts": agent_config.get("max_repair_attempts", 3)
        },
        "group_chat": {
            "max_consecutive_replies": agent_config.get("max_consecutive_replies", 10)
        }
    }
    
    # Add any agent-specific overrides from the config
    if config and "agent_overrides" in config:
        for agent_name, overrides in config["agent_overrides"].items():
            if agent_name in agent_configs:
                agent_configs[agent_name].update(overrides)
    
    return agent_configs

def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load full configuration from file or defaults.
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        Complete configuration dictionary
    """
    # Start with default configuration
    config = DEFAULT_CONFIG.copy()
    
    # Load from file if provided
    if config_path:
        file_config = load_config_from_file(config_path)
        _deep_update(config, file_config)
    
    # Create derived configurations
    config["llm_config"] = get_llm_config(config)
    config["database_config"] = get_database_config(config)
    config["agent_configs"] = create_agent_configs(config)
    
    return config

def _deep_update(d: Dict, u: Dict) -> Dict:
    """
    Deep update dictionary d with dictionary u.
    
    Args:
        d: Dictionary to update
        u: Dictionary with updates
        
    Returns:
        Updated dictionary
    """
    for k, v in u.items():
        if isinstance(v, dict) and k in d and isinstance(d[k], dict):
            _deep_update(d[k], v)
        else:
            d[k] = v
    return d 