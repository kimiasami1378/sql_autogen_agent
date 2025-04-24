import json
import re
from typing import Dict, Optional, List
from autogen import AssistantAgent

class ResultValidatorAgent(AssistantAgent):
    """Agent responsible for validating query results against expected output."""
    
    def __init__(self, name: str = "ResultValidator", **kwargs):
        system_message = """You are a Result Validator Agent. Your job is to:

1. Evaluate whether query results correctly answer the original question
2. Check if the format of results matches what was expected
3. Identify any potential discrepancies or missing information
4. Provide a pass/fail assessment with detailed reasoning

When validating results:
- Consider whether the returned data actually answers the question
- Check if the result is complete (includes all necessary data)
- Verify if the SQL query is correct for the question
- Ensure the data is formatted appropriately

Always format your response as follows:
```
VALIDATION ANALYSIS:
[Detailed analysis of the results and how they relate to the question]

VALIDATION ASSESSMENT:
[List specific points about what's correct or incorrect about the results]

VALIDATION: [PASS/FAIL]
```

IMPORTANT: Always end your response with either "VALIDATION: PASS" or "VALIDATION: FAIL".
"""
        super().__init__(name=name, system_message=system_message, **kwargs)
    
    async def generate_response(self, message: str) -> str:
        """Generate a response to a message using the LLM.
        
        This method allows for direct agent communication outside of a group chat.
        
        Args:
            message: The message to respond to
            
        Returns:
            The generated response
        """
        response = await self.llm_config["config_list"][0]["model"].generate_async(
            messages=[{"role": "system", "content": self.system_message},
                     {"role": "user", "content": message}]
        )
        return response.get("content", "")
    
    async def validate_results(self, question: str, sql_query: str, execution_result: Dict, expected_result: Optional[Dict] = None) -> Dict:
        """Validate whether the execution results match expectations."""
        # Construct validation message
        validation_prompt = f"""Please validate the SQL query results for this question:

QUESTION: {question}

SQL QUERY: 
{sql_query}

EXECUTION RESULT:
{json.dumps(execution_result, indent=2)}
"""

        if expected_result:
            validation_prompt += f"""
EXPECTED RESULT:
{json.dumps(expected_result, indent=2)}
"""

        # Request validation analysis
        response = await self.generate_response(validation_prompt)
        
        # Check the verdict
        is_valid = self._check_validation_verdict(response)
        
        return {
            "question": question,
            "sql_query": sql_query,
            "is_valid": is_valid,
            "explanation": response
        }
    
    def _check_validation_verdict(self, response: str) -> bool:
        """Check for validation verdict in the response."""
        response_upper = response.upper()
        
        # Check for our explicit format first
        if "VALIDATION: PASS" in response_upper:
            return True
        if "VALIDATION: FAIL" in response_upper:
            return False
            
        # Count positive and negative markers
        pass_markers = ["PASS", "CORRECT", "VALID", "SUCCESS"]
        fail_markers = ["FAIL", "INCORRECT", "INVALID", "ERROR"]
        
        pass_count = sum(1 for marker in pass_markers if marker in response_upper)
        fail_count = sum(1 for marker in fail_markers if marker in response_upper)
        
        # If we have both or neither, do a more detailed analysis
        if (pass_count > 0 and fail_count > 0) or (pass_count == 0 and fail_count == 0):
            # Look at the last few sentences which often contain the conclusion
            sentences = re.split(r'[.!?]', response)
            last_sentences = sentences[-3:] if len(sentences) >= 3 else sentences
            
            last_text = " ".join(last_sentences).upper()
            
            pass_in_conclusion = any(marker in last_text for marker in pass_markers)
            fail_in_conclusion = any(marker in last_text for marker in fail_markers)
            
            if pass_in_conclusion and not fail_in_conclusion:
                return True
            if fail_in_conclusion and not pass_in_conclusion:
                return False
                
            # If still ambiguous, default to the overall sentiment
            return pass_count > fail_count
        
        # Simple case: one type of marker present
        return pass_count > 0 