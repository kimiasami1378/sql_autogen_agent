import re
from typing import Dict, Optional
from autogen import AssistantAgent

class SQLGeneratorAgent(AssistantAgent):
    """Agent responsible for generating SQL queries from natural language questions."""
    
    def __init__(self, name: str = "SQLGenerator", **kwargs):
        system_message = """You are a SQL Generator Agent. Your job is to:

1. Convert natural language questions to syntactically and logically correct SQL queries
2. Ensure all table names, column names, and SQL syntax are correct
3. Use appropriate JOINs to connect related tables
4. Pay attention to proper WHERE clauses, aggregations, GROUP BY, HAVING, and ORDER BY
5. Provide thorough explanations of your generated SQL

You will receive:
- A natural language question
- An analysis of the question's requirements
- Database schema information

Respond with:
1. A brief explanation of your approach
2. The SQL query formatted in a code block using SQL syntax
3. A step-by-step explanation of how the query addresses the question

For complex questions, break them down into parts and explain your reasoning clearly.
"""
        super().__init__(name=name, system_message=system_message, **kwargs)
    
    def _extract_sql(self, text: str) -> str:
        """Extract SQL from text response."""
        # Pattern for SQL code blocks in markdown
        code_block_pattern = r"```sql\n(.*?)```"
        # Pattern for generic code blocks with SELECT statements
        generic_block_pattern = r"```\n(SELECT.*?)```"
        # Pattern for lines starting with SELECT and ending with semicolon
        select_line_pattern = r"(SELECT.*?;)"
        
        # Try to find markdown SQL blocks
        sql_blocks = re.findall(code_block_pattern, text, re.DOTALL)
        if sql_blocks:
            return sql_blocks[0].strip()
        
        # Try to find generic code blocks with SELECT
        generic_blocks = re.findall(generic_block_pattern, text, re.DOTALL)
        if generic_blocks:
            return generic_blocks[0].strip()
        
        # Try to find SELECT statements
        select_lines = re.findall(select_line_pattern, text, re.DOTALL)
        if select_lines:
            return select_lines[0].strip()
        
        # If no SQL found, return the text
        return text
        
    async def generate_response(self, message: str) -> str:
        """Generate a response to a message using the LLM.
        
        This method allows for direct agent communication outside of a group chat.
        """
        response = await self.llm_config["config_list"][0]["model"].generate_async(
            messages=[{"role": "system", "content": self.system_message},
                     {"role": "user", "content": message}]
        )
        return response.get("content", "") 