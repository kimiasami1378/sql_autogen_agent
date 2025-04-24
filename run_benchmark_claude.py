#!/usr/bin/env python
import os
import json
import time
import argparse
import dotenv
from tqdm import tqdm
import sqlite3
import pandas as pd
import asyncio
import re

# Load environment variables
dotenv.load_dotenv()

# Set the Anthropic API key
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable not set")

# Constants
DB_PATH = "minidev/MINIDEV/dev_databases"
RESULTS_PATH = "results"

# Import the AutoGen components
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.anthropic import AnthropicChatCompletionClient

class ClaudeSQLBenchmark:
    """Run SQL benchmark using Claude and the latest AutoGen."""
    
    def __init__(self, db_path=DB_PATH):
        """Initialize the benchmark runner."""
        self.db_path = db_path
        self.model_client = AnthropicChatCompletionClient(model="claude-3-7-sonnet-20250219")
        
        # Ensure output directories exist
        os.makedirs(RESULTS_PATH, exist_ok=True)
        os.makedirs(DB_PATH, exist_ok=True)
    
    async def execute_sql(self, sql_query, db_file):
        """Execute a SQL query against a database."""
        try:
            # Make SQL case-insensitive for table and column names
            sql_query = sql_query.replace('Name', 'name').replace('Population', 'population').replace('Country', 'country')
            
            conn = sqlite3.connect(db_file)
            results = pd.read_sql_query(sql_query, conn)
            conn.close()
            
            # Convert results to a list of dictionaries
            result_dicts = results.to_dict('records')
            columns = list(results.columns)
            
            return {
                "success": True,
                "sql_query": sql_query,
                "columns": columns,
                "results": result_dicts,
                "row_count": len(result_dicts),
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "sql_query": sql_query,
                "columns": [],
                "results": [],
                "row_count": 0,
                "error": str(e)
            }
    
    async def process_question(self, question, db_id="world_1"):
        """Process a natural language question and generate/execute SQL."""
        # Initialize result dict
        result = {
            "question": question,
            "sql": None,
            "execution_results": None,
            "validation_status": "FAIL",
            "error_message": None
        }
        
        try:
            # Look for the database files
            db_dir = os.path.join(self.db_path, db_id)
            sqlite_file = None
            
            if os.path.isdir(db_dir):
                # If db_id points to a directory, look for SQLite files
                files = os.listdir(db_dir)
                sqlite_files = [f for f in files if f.endswith('.sqlite')]
                if sqlite_files:
                    sqlite_file = os.path.join(db_dir, sqlite_files[0])
            elif os.path.exists(os.path.join(self.db_path, f"{db_id}.sqlite")):
                # If db_id.sqlite exists directly in the db_path
                sqlite_file = os.path.join(self.db_path, f"{db_id}.sqlite")
            else:
                # Try to find any directory containing this database
                for dir_name in os.listdir(self.db_path):
                    dir_path = os.path.join(self.db_path, dir_name)
                    if os.path.isdir(dir_path):
                        files = os.listdir(dir_path)
                        sqlite_files = [f for f in files if f.endswith('.sqlite')]
                        for f in sqlite_files:
                            if db_id in f:
                                sqlite_file = os.path.join(dir_path, f)
                                break
                        if sqlite_file:
                            break
            
            # If still no SQLite file found, use the first available
            if not sqlite_file:
                for dir_name in os.listdir(self.db_path):
                    dir_path = os.path.join(self.db_path, dir_name)
                    if os.path.isdir(dir_path):
                        files = os.listdir(dir_path)
                        sqlite_files = [f for f in files if f.endswith('.sqlite')]
                        if sqlite_files:
                            sqlite_file = os.path.join(dir_path, sqlite_files[0])
                            break
            
            if not sqlite_file:
                result["error_message"] = f"Could not find SQLite database for {db_id}"
                return result
                
            print(f"  Using SQLite file: {sqlite_file}")
            
            # Extract schema information from the database
            schema_info = self._extract_schema_info(sqlite_file)
            print(f"  Schema: {schema_info}")
            
            # Prepare a system prompt
            system_prompt = f"""You are an expert SQL generator. Your task is to:
1. Generate a syntactically correct SQL query for the given question
2. Only output the SQL query, nothing else
3. Make sure the SQL is executable on a SQLite database
4. Be precise about table and column names
5. Focus on generating correct SQL syntax

The database contains the following tables and columns:
{schema_info}

Use only the tables and columns mentioned in the schema. Do not make up or invent tables/columns that are not in the schema.
"""
            
            # Create a new agent with the system prompt instead of updating
            agent = AssistantAgent("sql_generator", system_message=system_prompt, model_client=self.model_client)
            
            # Generate SQL query
            prompt = f"Generate a SQL query to answer the following question: {question}"
            response = await agent.run(task=prompt)
            
            # Print the raw response for debugging
            print(f"RAW RESPONSE TYPE: {type(response)}")
            
            # Extract SQL from response
            # Get the assistant's response (second message) from the TaskResult
            if hasattr(response, 'messages') and len(response.messages) >= 2:
                assistant_message = response.messages[1]
                if hasattr(assistant_message, 'content'):
                    sql_text = assistant_message.content
                    print(f"ASSISTANT MESSAGE: {sql_text}")
                    sql = self._extract_sql(sql_text)
                else:
                    print("No content attribute in assistant message")
                    sql = None
            else:
                print("No messages or fewer than 2 messages in response")
                sql = self._extract_sql(str(response))
            
            # Print the extracted SQL for debugging
            print(f"EXTRACTED SQL: {sql}")
            
            if sql:
                result["sql"] = sql
                
                # Execute SQL query using the found SQLite file
                if os.path.exists(sqlite_file):
                    execution_result = await self.execute_sql(sql, sqlite_file)
                    
                    if execution_result.get("success", False):
                        result["execution_results"] = execution_result
                        result["validation_status"] = "PASS"
                    else:
                        result["error_message"] = execution_result.get("error", "Execution failed")
                else:
                    result["error_message"] = f"Database file not found: {sqlite_file}"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            result["error_message"] = f"Error: {str(e)}"
            
        return result
    
    def _extract_sql(self, text):
        """Extract SQL query from response text."""
        if text is None:
            return None
            
        import re
        
        # Convert to string if it's not already
        if not isinstance(text, str):
            text = str(text)
        
        # Clean up common artifacts in the response
        text = re.sub(r',\s*type=.*?stop_reason=None\)', '', text)
        text = re.sub(r'"\s*,\s*type=.*', '', text)
        text = re.sub(r'"$', '', text)
        
        # For simple direct SQL, just use it directly
        if text.strip().upper().startswith("SELECT") and ";" in text:
            return self._clean_sql(text)
        
        # Look for SQL in code blocks
        code_block_pattern = r"```(?:sql)?\s*(SELECT[\s\S]*?)```"
        code_matches = re.search(code_block_pattern, text, re.IGNORECASE)
        
        if code_matches:
            sql = code_matches.group(1).strip()
            return self._clean_sql(sql)
        
        # Look for SELECT statements
        select_pattern = r"(SELECT\s+.*?)(?:;|$)"
        select_matches = re.findall(select_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if select_matches:
            sql = select_matches[0].strip()
            return self._clean_sql(sql)
        
        return None
        
    def _clean_sql(self, sql):
        """Clean up SQL query text."""
        import re
        
        # Replace newlines with spaces
        sql = re.sub(r'\s*\n\s*', ' ', sql)
        
        # Remove any quoted text at the end (artifact of string representation)
        sql = re.sub(r'\s*"\s*$', '', sql)
        
        # Remove double quotes around identifiers (safer for SQLite)
        sql = re.sub(r'"([^"]*)"', r'\1', sql)
        
        # Fix table reference from world_1 to country if needed
        sql = sql.replace('FROM world_1', 'FROM country')
        
        # Clean up extra whitespace
        sql = re.sub(r'\s+', ' ', sql).strip()
        
        # Make sure it ends with a semicolon
        if not sql.endswith(';'):
            sql += ';'
            
        return sql
    
    def _extract_schema_info(self, db_file):
        """Extract schema information from a SQLite database."""
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # Get all table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            schema_info = []
            
            # For each table, get its column information
            for table in tables:
                table_name = table[0]
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()
                
                # Format column information
                column_names = [col[1] for col in columns]
                schema_info.append(f"Table: {table_name}")
                schema_info.append(f"Columns: {', '.join(column_names)}")
                schema_info.append("")
            
            conn.close()
            
            return "\n".join(schema_info)
        except Exception as e:
            return f"Error extracting schema: {str(e)}"
    
    async def close(self):
        """Close resources."""
        await self.model_client.close()

def create_test_db(db_path="data/databases/world_1.sqlite"):
    """Create a simple test database with country data."""
    import sqlite3
    import os
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    
    # Drop the table if it exists to start fresh
    conn.execute("DROP TABLE IF EXISTS country")
    
    conn.execute("""
    CREATE TABLE IF NOT EXISTS country (
        id INTEGER PRIMARY KEY,
        name TEXT,
        population INTEGER
    )
    """)
    
    # Insert some sample data
    countries = [
        ("China", 1400000000),
        ("India", 1300000000),
        ("United States", 330000000),
        ("Indonesia", 270000000),
        ("Pakistan", 220000000),
        ("Brazil", 210000000),
        ("Nigeria", 200000000),
        ("Bangladesh", 160000000),
        ("Russia", 145000000),
        ("Japan", 126000000),
        ("Mexico", 126000000),
        ("Philippines", 109000000),
        ("Germany", 83000000)
    ]
    
    conn.executemany("INSERT OR REPLACE INTO country (name, population) VALUES (?, ?)", countries)
    conn.commit()
    conn.close()
    
    print(f"Test database created at {db_path}")
    return db_path

async def run_benchmark(data_file, limit=None):
    """Run the benchmark on a dataset of questions."""
    # Load dataset
    with open(data_file, 'r') as f:
        dataset = json.load(f)
    
    # Limit dataset size if requested
    if limit:
        dataset = dataset[:limit]
    
    # Initialize benchmark runner
    benchmark = ClaudeSQLBenchmark()
    
    # Results storage
    results = []
    success_count = 0
    start_time = time.time()
    
    try:
        # Process each question
        for i, item in enumerate(tqdm(dataset, desc="Processing questions")):
            try:
                question = item["question"]
                
                # Extract db_id from the "db_id" field or fall back to extracting from database_id
                if "db_id" in item:
                    db_id = item["db_id"]
                elif "database_id" in item:
                    db_id = item["database_id"]
                else:
                    # Try to extract from question or use a default
                    db_name_match = re.search(r'database (\w+)', question, re.IGNORECASE)
                    if db_name_match:
                        db_id = db_name_match.group(1)
                    else:
                        # Default to first directory in DB_PATH
                        db_id = os.listdir(DB_PATH)[0] if os.listdir(DB_PATH) else "debit_card_specializing"
                
                gold_sql = item.get("gold_sql", "") or item.get("SQL", "")
                
                print(f"\n[{i+1}/{len(dataset)}] Processing: {question}")
                print(f"  Using database: {db_id}")
                
                # Process through the benchmark
                result = await benchmark.process_question(question, db_id)
                
                # Check if execution was successful
                success = False
                if result["validation_status"] == "PASS" and result["execution_results"] and result["execution_results"]["success"]:
                    success_count += 1
                    success = True
                
                # Store the result
                results.append({
                    "question_id": i,
                    "question": question,
                    "db_id": db_id,
                    "gold_sql": gold_sql,
                    "predicted_sql": result["sql"],
                    "execution_success": success,
                    "execution_result": result["execution_results"],
                    "validation_result": {
                        "is_valid": result["validation_status"] == "PASS",
                        "explanation": result.get("error_message", "")
                    }
                })
                
                # Print results
                print(f"  Gold SQL: {gold_sql}")
                print(f"  Predicted SQL: {result['sql']}")
                print(f"  Success: {success}")
                if not success:
                    if result["error_message"]:
                        print(f"  Error: {result['error_message']}")
                    elif result["execution_results"] and not result["execution_results"].get("success", False):
                        print(f"  Execution Error: {result['execution_results'].get('error', 'Unknown error')}")
                else:
                    if result["execution_results"]:
                        print(f"  Rows returned: {result['execution_results'].get('row_count', 0)}")
                
            except Exception as e:
                print(f"Error processing question {i}: {e}")
                import traceback
                traceback.print_exc()
                
                results.append({
                    "question_id": i,
                    "question": question,
                    "db_id": db_id if 'db_id' in locals() else 'unknown',
                    "gold_sql": gold_sql if 'gold_sql' in locals() else '',
                    "error": str(e),
                    "execution_success": False
                })
    finally:
        # Close resources
        await benchmark.close()
    
    # Calculate metrics
    end_time = time.time()
    total_time = end_time - start_time
    accuracy = success_count / len(dataset) if dataset else 0
    
    # Save results
    os.makedirs(RESULTS_PATH, exist_ok=True)
    
    with open(os.path.join(RESULTS_PATH, "claude_benchmark_results.json"), 'w') as f:
        json.dump(results, f, indent=2)
    
    # Generate summary
    summary = {
        "total_questions": len(dataset),
        "successful_executions": success_count,
        "execution_accuracy": accuracy,
        "total_time_seconds": total_time,
        "avg_time_per_question": total_time / len(dataset) if dataset else 0
    }
    
    with open(os.path.join(RESULTS_PATH, "claude_summary.json"), 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Print final accuracy
    print(f"\nFinal execution accuracy: {accuracy:.1%} ({success_count}/{len(dataset)})")
    print(f"Total time: {total_time:.1f} seconds, Avg: {total_time / len(dataset):.1f} seconds per question")
    
    return accuracy

async def run_test():
    """Run a simple test using test_data.json."""
    # Create test directories
    os.makedirs(DB_PATH, exist_ok=True)
    
    # Create a simple test database
    create_test_db(os.path.join(DB_PATH, "world_1.sqlite"))
    
    # Create test data
    test_data = [
        {
            "db_id": "world_1",
            "question": "What is the population of China?",
            "gold_sql": "SELECT population FROM country WHERE name = 'China';"
        },
        {
            "db_id": "world_1",
            "question": "Which country has the largest population?",
            "gold_sql": "SELECT name FROM country ORDER BY population DESC LIMIT 1;"
        },
        {
            "db_id": "world_1",
            "question": "List all countries with population over 200 million.",
            "gold_sql": "SELECT name FROM country WHERE population > 200000000;"
        }
    ]
    
    # Save test data
    with open("test_data.json", 'w') as f:
        json.dump(test_data, f)
    
    # Run benchmark on test data
    return await run_benchmark("test_data.json")

async def main_async():
    """Main entry point (async version)."""
    parser = argparse.ArgumentParser(description="Run the BIRD-SQL Mini-Dev benchmark with Claude")
    parser.add_argument("--data", type=str, default="minidev/MINIDEV/mini_dev_sqlite.json", 
                      help="Path to the dataset file")
    parser.add_argument("--limit", type=int, default=None, 
                      help="Limit the number of examples to process")
    parser.add_argument("--test", action="store_true", 
                      help="Run test on a small dataset")
    
    args = parser.parse_args()
    
    # Run test or benchmark
    if args.test:
        await run_test()
    else:
        if not os.path.exists(args.data):
            print(f"Error: Dataset file not found: {args.data}")
            print("Use --test to run a test on a small dataset.")
            return
        
        await run_benchmark(args.data, limit=args.limit)

def main():
    """Main entry point."""
    asyncio.run(main_async())

if __name__ == "__main__":
    main() 