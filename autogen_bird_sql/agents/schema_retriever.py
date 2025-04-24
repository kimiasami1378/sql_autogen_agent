import os
import json
import sqlite3
from typing import Dict
from autogen import AssistantAgent

class SchemaRetrieverAgent(AssistantAgent):
    """Agent responsible for retrieving and formatting database schema information."""
    
    def __init__(self, name: str = "SchemaRetriever", **kwargs):
        system_message = """You are a Schema Retriever Agent. Your job is to:

1. Examine the question and analysis to identify needed database tables and columns
2. Retrieve the relevant schema information from the database
3. Format the schema in a way that's useful for SQL generation
4. Provide create table statements, column descriptions, and relationships

Always include:
- Full column names including datatypes
- Primary keys marked as PRIMARY KEY
- Foreign key relationships
- Any indexes or constraints that may be relevant

Focus on providing comprehensive schema information that will be needed to construct an accurate SQL query.
"""
        super().__init__(name=name, system_message=system_message, **kwargs)
    
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
        """Set or update the database path.
        
        Args:
            db_path: Path to the SQLite database file or directory
        """
        self.db_path = db_path
        
    def _get_schema_info(self, db_path: str, db_id: str) -> str:
        """Retrieve and format database schema information.
        
        Args:
            db_path: Directory containing the database files
            db_id: Database identifier
            
        Returns:
            Formatted string containing schema information
        """
        db_file = os.path.join(db_path, f"{db_id}.sqlite")
        
        if not os.path.exists(db_file):
            return f"Schema information not available: Database file {db_file} not found."
        
        try:
            # Connect to the database
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # Get list of tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            schema_info = []
            schema_info.append(f"Database: {db_id}")
            schema_info.append(f"Tables: {len(tables)}")
            schema_info.append("")
            
            # Get details for each table
            for table in tables:
                table_name = table[0]
                
                # Skip SQLite internal tables
                if table_name.startswith('sqlite_'):
                    continue
                
                # Get table schema (column definitions)
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()
                
                schema_info.append(f"Table: {table_name}")
                schema_info.append("Columns:")
                
                for col in columns:
                    col_id, name, data_type, not_null, default_val, is_pk = col
                    pk_marker = "PRIMARY KEY" if is_pk else ""
                    null_marker = "NOT NULL" if not_null else ""
                    default = f"DEFAULT {default_val}" if default_val is not None else ""
                    
                    schema_info.append(f"  - {name} ({data_type}) {pk_marker} {null_marker} {default}".strip())
                
                # Get foreign keys
                cursor.execute(f"PRAGMA foreign_key_list({table_name});")
                foreign_keys = cursor.fetchall()
                
                if foreign_keys:
                    schema_info.append("Foreign Keys:")
                    for fk in foreign_keys:
                        fk_id, seq, ref_table, from_col, to_col, on_update, on_delete, match = fk
                        schema_info.append(f"  - {from_col} -> {ref_table}({to_col})")
                
                schema_info.append("")
            
            conn.close()
            return "\n".join(schema_info)
            
        except Exception as e:
            return f"Error retrieving schema information: {str(e)}" 