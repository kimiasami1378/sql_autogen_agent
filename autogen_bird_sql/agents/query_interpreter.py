from typing import Dict
from autogen import AssistantAgent

class QueryInterpreterAgent(AssistantAgent):
    """Agent responsible for parsing natural language questions and identifying relevant tables/columns."""
    
    def __init__(self, name: str = "QueryInterpreter", **kwargs):
        system_message = """You are a Query Interpreter Agent. Your job is to:

1. Parse natural language questions about a database
2. Identify the key entities, attributes, and relationships required to answer the question
3. Clarify any ambiguities in the question
4. Provide a concise analysis that can be used to construct an appropriate SQL query

Your analysis should include:
- Main entities/tables needed
- Relevant columns to select or filter
- Required joins or relationships
- Conditions or constraints from the question
- Sorting, grouping, or aggregation needed

Focus on understanding what the question is truly asking for and how to translate it to a database query structure.
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