#!/usr/bin/env python
"""
Group Chat Demo for BirdSQLOrchestrator

This script demonstrates how to use the group chat functionality of the BirdSQLOrchestrator.
It initializes the orchestrator, configures the agents, and processes a natural language query.
"""

import os
import sys
import json
import argparse
import dotenv
from pathlib import Path

# Ensure the autogen_bird_sql package is in the Python path
sys.path.append(str(Path(__file__).parent.parent))

from autogen_bird_sql.orchestrator import BirdSQLOrchestrator

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Demonstrate BirdSQLOrchestrator group chat')
    parser.add_argument('--db_path', type=str, default='./data/databases',
                        help='Path to the directory containing SQLite databases')
    parser.add_argument('--question', type=str, 
                        default='What is the population of China?',
                        help='Natural language question to process')
    parser.add_argument('--config', type=str, default='./examples/config.yaml',
                        help='Path to configuration file (YAML or JSON)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug output')
    args = parser.parse_args()
    
    # Load environment variables from .env file if it exists
    dotenv.load_dotenv()
    
    # Check for OpenAI API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable not set.")
        print("Please set it in your environment or in a .env file.")
        sys.exit(1)
    
    # Check if config file exists
    config_path = args.config if os.path.exists(args.config) else None
    if args.config and not config_path:
        print(f"WARNING: Config file not found at {args.config}, using defaults")
    
    # Initialize the orchestrator with configuration
    print(f"Initializing BirdSQLOrchestrator with:")
    print(f"- Database path: {args.db_path}")
    print(f"- Config file: {config_path or 'default'}")
    orchestrator = BirdSQLOrchestrator(args.db_path, config_path=config_path)
    
    # Force debug mode if requested via command line
    if args.debug:
        orchestrator.debug_mode = True
    else:
        # Otherwise, ensure we're using group chat unless debug_mode is explicitly set
        orchestrator.debug_mode = False
    
    # Process the question
    print(f"\nProcessing question: '{args.question}'")
    print(f"Using {'direct agent communication' if orchestrator.debug_mode else 'group chat'} mode")
    print("=" * 80)
    
    result = orchestrator.process_question(args.question)
    
    # Display the results
    print("\nResults:")
    print("=" * 80)
    print(f"SQL Query: {result.get('sql')}")
    print("-" * 40)
    
    # Handle execution results
    execution_results = result.get('execution_results', {})
    if execution_results and execution_results.get('success', False):
        print("Execution Results:")
        results = execution_results.get('results', [])
        if results:
            # Print column headers
            columns = execution_results.get('columns', [])
            if columns:
                print(" | ".join(columns))
                print("-" * (sum(len(col) for col in columns) + (len(columns) - 1) * 3))
            
            # Print each row
            for row in results:
                if isinstance(row, dict):
                    print(" | ".join(str(row.get(col, '')) for col in columns))
                else:
                    print(row)
        else:
            print("No results returned.")
    else:
        print(f"Execution Failed: {execution_results.get('error', 'Unknown error')}")
    
    print("-" * 40)
    print(f"Validation Status: {result.get('validation_status', 'UNKNOWN')}")
    
    # Print error message if any
    error_message = result.get('error_message')
    if error_message:
        print(f"Error: {error_message}")
    
    # If in debug mode, print the full result dictionary
    if args.debug:
        print("\nFull Result Object:")
        print("=" * 80)
        print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main() 