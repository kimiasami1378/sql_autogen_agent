"""Configuration settings for the MAC-SQL AutoGen system."""

# OpenAI model configuration
OPENAI_CONFIG = {
    "model": "gpt-4",  # or "gpt-3.5-turbo" for faster but less accurate results
    "temperature": 0.2,  # Lower temperature for more deterministic outputs
    "max_tokens": 2000,  # Maximum tokens for model responses
    "top_p": 0.95,
}

# Default paths
DEFAULT_DATA_PATH = "datasets/mini_dev/validation.json"
DEFAULT_SCHEMA_PATH = "schemas"
DEFAULT_DB_PATH = "databases"
DEFAULT_RESULTS_PATH = "results"

# Agent parameters
MAX_REPAIR_ATTEMPTS = 3  # Maximum number of repair attempts for a failing query
