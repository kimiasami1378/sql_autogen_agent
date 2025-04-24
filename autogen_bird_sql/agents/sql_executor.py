import os
import json
import sqlite3
import pandas as pd
from typing import Dict, List, Optional, Union
from autogen import AssistantAgent

class SQLExecutorAgent(AssistantAgent):
    """Agent responsible for executing SQL queries and providing execution results."""
    
    def __init__(self, name: str = "SQLExecutor", db_path: str = None, **kwargs):
        """Initialize the SQL Executor Agent.
        
        Args:
            name: Name of the agent
            db_path: Path to the SQLite database
        """
        self.db_path = db_path
        
        system_message = """You are a SQL Executor Agent. Your job is to:

1. Execute SQL queries against a SQLite database
2. Return the execution results along with informative error messages if execution fails
3. Present query results in a readable tabular format
4. Provide insights about the results to help with validation

When errors occur, you will:
- Clearly identify the error type and location
- Suggest possible fixes
- Format error messages in a helpful way

Always include both the SQL query and the execution results in your responses.
"""
        super().__init__(name=name, system_message=system_message, **kwargs)
    
    async def execute_sql(self, sql_query: str) -> Dict:
        """Execute the SQL query and return the results."""
        try:
            conn = sqlite3.connect(self.db_path)
            results = pd.read_sql_query(sql_query, conn)
            conn.close()
            
            # Convert results to a list of dictionaries for easier serialization
            result_dicts = results.to_dict('records')
            columns = list(results.columns)
            
            return {
                "success": True,
                "sql_query": sql_query,
                "columns": columns,
                "results": result_dicts,
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "sql_query": sql_query,
                "columns": [],
                "results": [],
                "error": str(e)
            }
    
    def format_results_as_table(self, columns: List[str], results: List[Dict]) -> str:
        """Format the SQL results as a readable text table."""
        if not results:
            return "No results found."
        
        # Calculate the maximum width for each column
        col_widths = {col: len(col) for col in columns}
        for row in results:
            for col in columns:
                col_widths[col] = max(col_widths[col], len(str(row.get(col, ''))))
        
        # Create the header
        header = " | ".join(col.ljust(col_widths[col]) for col in columns)
        separator = "-" * len(header)
        
        # Create the rows
        rows = []
        for row in results:
            rows.append(" | ".join(str(row.get(col, '')).ljust(col_widths[col]) for col in columns))
        
        # Combine everything
        table = f"{header}\n{separator}\n" + "\n".join(rows)
        return table
    
    async def generate_response(self, message: str) -> str:
        """Generate a response to a message using the LLM.
        
        This method allows for direct agent communication outside of a group chat.
        """
        response = await self.llm_config["config_list"][0]["model"].generate_async(
            messages=[{"role": "system", "content": self.system_message},
                     {"role": "user", "content": message}]
        )
        return response.get("content", "")

    def set_db_path(self, db_path: str):
        """Set the path to the SQLite database."""
        self.db_path = db_path
    
    def _execute_query(self, db_path: str, db_id: str, query: str) -> Dict:
        """Execute a SQL query and return the results."""
        db_file = os.path.join(db_path, f"{db_id}.sqlite")
        
        if not os.path.exists(db_file):
            return {
                "success": False,
                "results": None,
                "row_count": 0,
                "error": f"Database file not found: {db_file}"
            }
        
        try:
            conn = sqlite3.connect(db_file)
            conn.text_factory = lambda b: b.decode(errors='ignore')  # Handle text encoding issues
            
            # Execute the query
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            # Convert to dictionary format
            results = df.to_dict('records')
            
            return {
                "success": True,
                "results": results,
                "row_count": len(results),
                "error": None
            }
        
        except Exception as e:
            error_message = str(e)
            
            # Enhance error message with context
            if "no such table" in error_message.lower():
                table_name = error_message.split("no such table: ")[1].split()[0] if "no such table: " in error_message else "unknown"
                error_message += f"\nTable '{table_name}' does not exist in the database."
            
            elif "no such column" in error_message.lower():
                column_name = error_message.split("no such column: ")[1].split()[0] if "no such column: " in error_message else "unknown"
                error_message += f"\nColumn '{column_name}' does not exist in the table."
            
            return {
                "success": False,
                "results": None,
                "row_count": 0,
                "error": error_message
            } 