import re
from typing import Dict, Optional
from autogen import AssistantAgent

class AutoRepairAgent(AssistantAgent):
    """Agent responsible for analyzing SQL execution errors and providing repair guidance."""
    
    def __init__(self, name: str = "AutoRepair", **kwargs):
        system_message = """You are a SQL Error Analysis and Repair Agent. Your job is to:

1. Analyze SQL execution errors in detail
2. Identify the root cause of issues
3. Provide specific repair guidance to fix the SQL query
4. Explain why the changes will fix the problem

When analyzing errors and providing repair guidance:
- Be specific about what's wrong in the SQL
- Provide exact syntax corrections
- Explain common SQL mistakes (like missing JOINs, incorrect table/column names)
- Consider schema constraints and requirements
- Always provide a repaired SQL query that should work

Your repair guidance should follow this format:
```
ERROR ANALYSIS:
[Detailed analysis of what went wrong]

ROOT CAUSE:
[Concise statement of the root cause]

REPAIR GUIDANCE:
[Specific steps to fix the issue]

REPAIRED SQL QUERY:
[Complete corrected SQL query]

EXPLANATION:
[Why this fix addresses the problem]
```
"""
        super().__init__(name=name, system_message=system_message, **kwargs)
    
    async def repair_sql(self, original_sql: str, error_message: str, schema_description: str) -> Dict:
        """Generate repair guidance for a failed SQL query."""
        
        # Construct the message for the repair guidance
        repair_message = f"""I need to repair a SQL query that failed.

ORIGINAL SQL:
{original_sql}

ERROR MESSAGE:
{error_message}

DATABASE SCHEMA:
{schema_description}

Please analyze the error and provide repair guidance following the format in your instructions.
"""
        
        # Generate the repair guidance
        response = await self.generate_response(repair_message)
        
        # Extract the repaired SQL query from the response
        repaired_sql = self._extract_sql(response)
        
        return {
            "original_sql": original_sql,
            "error": error_message,
            "repair_guidance": response,
            "repaired_sql": repaired_sql
        }
    
    async def generate_response(self, message: str) -> str:
        """Generate a response to a message using the LLM.
        
        This method allows for direct agent communication outside of a group chat.
        """
        response = await self.llm_config["config_list"][0]["model"].generate_async(
            messages=[{"role": "system", "content": self.system_message},
                     {"role": "user", "content": message}]
        )
        return response.get("content", "")
    
    def _extract_sql(self, text: str) -> Optional[str]:
        """Extract the SQL query from the repair guidance."""
        # Look for SQL between "REPAIRED SQL QUERY:" and the next section or end of text
        repaired_sql_pattern = r"REPAIRED SQL QUERY:\s*\n(.*?)(?:\n\n[A-Z ]+:|$)"
        sql_match = re.search(repaired_sql_pattern, text, re.DOTALL)
        
        if sql_match:
            # Extract and clean the SQL query
            sql = sql_match.group(1).strip()
            
            # Remove any markdown code block syntax
            sql = re.sub(r'^```sql\s*|\s*```$', '', sql, flags=re.MULTILINE)
            sql = re.sub(r'^```\s*|\s*```$', '', sql, flags=re.MULTILINE)
            
            return sql.strip()
        
        # Fallback: try to find SQL code blocks
        code_block_pattern = r"```(?:sql)?\s*(SELECT[\s\S]*?);?\s*```"
        code_blocks = re.findall(code_block_pattern, text, re.IGNORECASE)
        
        if code_blocks:
            return code_blocks[0].strip()
        
        # Fallback: look for lines starting with SELECT
        select_lines_pattern = r"(?:^|\n)(SELECT[\s\S]*?);(?:$|\n)"
        select_matches = re.findall(select_lines_pattern, text, re.IGNORECASE)
        
        if select_matches:
            return select_matches[0].strip()
        
        # If no SQL found, return None
        return None 