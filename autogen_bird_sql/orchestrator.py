#!/usr/bin/env python
import os
import json
import dotenv
import re
from typing import Dict, Optional, List, Any
from autogen import GroupChat, GroupChatManager, UserProxyAgent

from autogen_bird_sql.agents import (
    QueryInterpreterAgent,
    SchemaRetrieverAgent,
    SQLGeneratorAgent,
    SQLExecutorAgent,
    ResultValidatorAgent,
    AutoRepairAgent,
)

from autogen_bird_sql.config import load_config, DEFAULT_CONFIG

# Load environment variables
dotenv.load_dotenv()

# Disable Docker usage in Autogen
os.environ["AUTOGEN_USE_DOCKER"] = "0"

# Constants
MAX_REPAIR_ATTEMPTS = 3
MAX_CONSECUTIVE_AUTO_REPLY = 10  # Limit conversation rounds to prevent infinite loops

class BirdSQLOrchestrator:
    """Orchestration manager for multi-agent text-to-SQL processing."""
    
    def __init__(self, db_path: str, config_path: str = None):
        """Initialize the orchestrator with database path and configuration.
        
        Args:
            db_path: Path to the directory containing SQLite databases
            config_path: Optional path to configuration file
        """
        # Load configuration
        config = load_config(config_path)
        config["database"]["path"] = db_path  # Override db_path with the provided path
        
        self.db_path = db_path
        self.debug_mode = False  # Set debug mode to False to use group chat
        
        # Initialize LLM config for all agents
        self.llm_config = config["llm_config"]
        
        # Create the specialized SQL agents
        self.agents = self._create_agents()
    
    def _create_agents(self) -> Dict:
        """Create all the specialized agents for text-to-SQL tasks."""
        agents = {}
        
        # Query interpreter agent
        agents["interpreter"] = QueryInterpreterAgent(
            name="QueryInterpreter",
            llm_config=self.llm_config
        )
        
        # Schema retriever agent
        agents["schema"] = SchemaRetrieverAgent(
            name="SchemaRetriever",
            llm_config=self.llm_config
        )
        # Set the database path after initialization
        if hasattr(agents["schema"], "set_db_path"):
            agents["schema"].set_db_path(self.db_path)
        
        # SQL generator agent
        agents["generator"] = SQLGeneratorAgent(
            name="SQLGenerator",
            llm_config=self.llm_config
        )
        
        # SQL executor agent
        agents["executor"] = SQLExecutorAgent(
            name="SQLExecutor",
            llm_config=self.llm_config
        )
        # Set the database path after initialization
        agents["executor"].set_db_path(self.db_path)
        
        # Result validator agent
        agents["validator"] = ResultValidatorAgent(
            name="ResultValidator",
            llm_config=self.llm_config
        )
        
        # Auto repair agent
        agents["repair"] = AutoRepairAgent(
            name="AutoRepair",
            llm_config=self.llm_config
        )
        
        # Create user proxy agent for initiating conversations
        agents["user"] = UserProxyAgent(
            name="User",
            human_input_mode="NEVER",
            is_termination_msg=lambda x: False,
            code_execution_config=False,
        )
        
        return agents
    
    def _setup_group_chat(self, question: str, db_id: str) -> GroupChatManager:
        """Set up the group chat with all agent participants and define the conversation flow.
        
        Args:
            question: The natural language question being processed
            db_id: Database identifier
            
        Returns:
            Configured GroupChatManager ready to run the conversation
        """
        # Create a list of agents for the group chat
        agent_list = [
            self.agents["user"],
            self.agents["interpreter"],
            self.agents["schema"],
            self.agents["generator"],
            self.agents["executor"],
            self.agents["validator"],
            self.agents["repair"]
        ]
        
        # Define a function to determine the next speaker based on the conversation
        def select_next_speaker(messages, sender):
            """Determine the next speaker in the conversation based on message content."""
            if not messages:
                # If no messages yet, QueryInterpreter starts by analyzing the question
                return self.agents["interpreter"]
            
            last_message = messages[-1]
            last_speaker_name = last_message.get("name", "")
            last_content = last_message.get("content", "").lower()
            
            # Define the conversation flow logic
            if sender == self.agents["user"]:
                # After the user speaks, the QueryInterpreter analyzes the question
                return self.agents["interpreter"]
            
            elif sender == self.agents["interpreter"]:
                # After question interpretation, retrieve schema information
                return self.agents["schema"]
            
            elif sender == self.agents["schema"]:
                # After schema retrieval, generate SQL
                return self.agents["generator"]
            
            elif sender == self.agents["generator"]:
                # After SQL generation, execute the query
                sql_pattern = r"```(?:sql)?[\s\n]*(SELECT[\s\S]*?)[\s\n]*```"
                if re.search(sql_pattern, last_content, re.IGNORECASE):
                    return self.agents["executor"]
                # If no SQL was generated, ask the interpreter to clarify
                else:
                    return self.agents["interpreter"]
            
            elif sender == self.agents["executor"]:
                # After execution, validate the results or repair if there's an error
                if "error" in last_content.lower():
                    return self.agents["repair"]
                else:
                    return self.agents["validator"]
            
            elif sender == self.agents["validator"]:
                # After validation, either end the conversation or request repair if needed
                if "validation: pass" in last_content.lower():
                    # Conversation can end here if validation passes
                    return None
                elif "validation: fail" in last_content.lower():
                    return self.agents["repair"]
                else:
                    # If unclear, default to the repair agent
                    return self.agents["repair"]
            
            elif sender == self.agents["repair"]:
                # After repair guidance, the generator should create a new query
                if "repaired sql query" in last_content.lower():
                    return self.agents["generator"]
                else:
                    # If repair is unclear or incomplete, ask generator to try again
                    return self.agents["generator"]
            
            # Default case - if flow is unclear, the user agent can summarize and reset
            return self.agents["user"]
        
        # Create the group chat with custom next-speaker selection
        group_chat = GroupChat(
            agents=agent_list,
            messages=[],
            max_round=MAX_CONSECUTIVE_AUTO_REPLY,
            speaker_selection_method=select_next_speaker
        )
        
        # Create the group chat manager
        manager = GroupChatManager(
            groupchat=group_chat,
            llm_config=self.llm_config
        )
        
        return manager
    
    def _extract_results(self, chat_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract processing results from chat history."""
        results = {
            "sql": None,
            "execution_results": None,
            "validation_status": None,
            "error_message": None
        }
        
        # Pattern for extracting SQL query
        sql_patterns = [
            r"SQL QUERY:\s*(.*?)(?=\n\n|$)",  # Original pattern
            r"```sql\s*(.*?)\s*```",  # SQL in code block
            r"```\s*(SELECT.*?)\s*```",  # SQL in generic code block
            r"REPAIRED SQL QUERY:\s*(.*?)(?=\n\n|\n[A-Z]|$)"  # From repair agent
        ]
        
        # Pattern for extracting execution results
        exec_patterns = [
            r"EXECUTION RESULTS:\s*(.*?)(?=\n\n|$)",
            r"RESULT:\s*(\{.*?\})(?=\n\n|$)"
        ]
        
        # Pattern for extracting validation status
        validation_patterns = [
            r"VALIDATION:\s*(PASS|FAIL)(?:\s*(.*?))?(?=\n\n|$)",
            r"VALIDATION STATUS:\s*(PASS|FAIL)(?:\s*(.*?))?(?=\n\n|$)"
        ]
        
        # Pattern for extracting error message
        error_patterns = [
            r"SQL ERROR:\s*(.*?)(?=\n\n|$)",
            r"ERROR:\s*(.*?)(?=\n\n|$)",
            r"ERROR ANALYSIS:\s*(.*?)(?=\n\n|$)"
        ]
        
        for message in chat_history:
            content = message.get("content", "")
            
            # Extract SQL query if not already found
            if results["sql"] is None:
                for pattern in sql_patterns:
                    sql_match = re.search(pattern, content, re.DOTALL)
                    if sql_match:
                        # Clean up SQL (remove trailing semicolons and whitespace)
                        sql = sql_match.group(1).strip()
                        results["sql"] = sql
                        break
            
            # Extract execution results if not already found
            if results["execution_results"] is None:
                for pattern in exec_patterns:
                    exec_match = re.search(pattern, content, re.DOTALL)
                    if exec_match:
                        try:
                            results["execution_results"] = json.loads(exec_match.group(1).strip())
                        except json.JSONDecodeError:
                            # If we can't parse it as JSON, store it as raw output
                            if "raw_output" not in results:
                                results["raw_output"] = exec_match.group(1).strip()
                        break
            
            # Extract validation status if not already found
            if results["validation_status"] is None:
                for pattern in validation_patterns:
                    validation_match = re.search(pattern, content, re.DOTALL)
                    if validation_match:
                        results["validation_status"] = validation_match.group(1).strip()
                        # If there's a failure explanation, capture it
                        if validation_match.group(2):
                            results["error_message"] = validation_match.group(2).strip()
                        break
            
            # Extract error message if not already found
            if results["error_message"] is None:
                for pattern in error_patterns:
                    error_match = re.search(pattern, content, re.DOTALL)
                    if error_match:
                        results["error_message"] = error_match.group(1).strip()
                        break
        
        return results
    
    def process_question(self, question: str) -> Dict:
        """Process a natural language question and return SQL results.
        
        Args:
            question: String containing the natural language question
            
        Returns:
            Dictionary with processing results including SQL and execution output
        """
        # Initialize result dict
        result = {
            "question": question,
            "sql": None,
            "execution_results": None,
            "validation_status": "FAIL",
            "error_message": None
        }
        
        # Extract database ID from the question if present
        db_id = "world_1"  # Default database ID
        
        # Try to find a database ID in the question
        db_id_match = re.search(r"database (\w+)", question.lower())
        if db_id_match:
            db_id = db_id_match.group(1)
        
        try:
            # The following is the proper implementation using group chat
            # Set up the group chat for multi-agent communication
            manager = self._setup_group_chat(question=question, db_id=db_id)
            
            # Configure schema retriever with the correct database
            schema_file_path = os.path.join(self.db_path, f"{db_id}.sqlite")
            if hasattr(self.agents["schema"], "set_db_path"):
                self.agents["schema"].set_db_path(schema_file_path)
            
            # Formulate initial message to start the conversation
            initial_message = f"""USER QUESTION: {question}
            
This is a database question that needs to be answered by converting it to SQL and executing the query.
First, interpret the question to understand what it's asking for.
Then, retrieve the database schema to understand the available tables and columns.
Next, generate a valid SQL query based on the question and schema.
Finally, execute the query and validate the results."""
            
            # Run the group chat with a specific termination function
            response = manager.run(
                self.agents["user"], 
                message=initial_message,
                max_turns=MAX_CONSECUTIVE_AUTO_REPLY
            )
            
            # Process the chat history from the response
            chat_history = self._get_chat_history(response)
            
            # Extract results from the chat history
            extracted_results = self._extract_results(chat_history)
            
            # Update the result dictionary with the extracted results
            if extracted_results["sql"]:
                result["sql"] = extracted_results["sql"]
            if extracted_results["execution_results"]:
                result["execution_results"] = extracted_results["execution_results"]
            if extracted_results["validation_status"]:
                result["validation_status"] = extracted_results["validation_status"]
            if extracted_results["error_message"]:
                result["error_message"] = extracted_results["error_message"]
            
            # If we have SQL but no execution results, execute it directly
            if result["sql"] and result["execution_results"] is None:
                # Determine the specific database file path
                db_file_path = os.path.join(self.db_path, f"{db_id}.sqlite")
                
                if os.path.exists(db_file_path):
                    # Set the database path for the executor
                    self.agents["executor"].set_db_path(db_file_path)
                    
                    # Execute the SQL query
                    execution_result = self.agents["executor"].execute_sql(result["sql"])
                    
                    # Update results based on execution success/failure
                    if execution_result and execution_result.get("success", False):
                        result["execution_results"] = execution_result
                        result["validation_status"] = "PASS"
                    else:
                        # If execution failed, try to repair the SQL query
                        try:
                            # Get schema for the database
                            schema_description = self._get_schema_description(db_id)
                            
                            # Attempt to repair the SQL query using the AutoRepairAgent
                            error_message = execution_result.get("error", "Unknown error")
                            repair_result = self.agents["repair"].repair_sql(
                                original_sql=result["sql"],
                                error_message=error_message,
                                schema_description=schema_description
                            )
                            
                            if isinstance(repair_result, dict) and repair_result.get("repaired_sql"):
                                # Try executing the repaired SQL
                                result["sql"] = repair_result["repaired_sql"]
                                repair_execution = self.agents["executor"].execute_sql(result["sql"])
                                
                                # Update results with the repair attempt
                                if repair_execution and repair_execution.get("success", False):
                                    result["execution_results"] = repair_execution
                                    result["validation_status"] = "PASS"
                                else:
                                    result["error_message"] = f"Repair failed: {repair_execution.get('error', 'Unknown error')}"
                            else:
                                result["error_message"] = f"Could not repair SQL: {error_message}"
                        except Exception as repair_error:
                            result["error_message"] = f"Error during SQL repair: {str(repair_error)}"
                else:
                    result["error_message"] = f"Database file not found: {db_file_path}"
                    
        except Exception as e:
            # Handle any exceptions during processing
            result["error_message"] = f"Error: {str(e)}"
            
        return result
    
    def _get_chat_history(self, response):
        """Extract chat history from the chat response."""
        chat_history = []
        
        # Handle different response structures
        if hasattr(response, "chat_history"):
            # New Autogen API format
            return response.chat_history
        elif hasattr(response, "messages"):
            # Alternative format
            for msg in response.messages:
                chat_history.append({
                    "role": msg.role if hasattr(msg, "role") else "assistant",
                    "content": msg.content if hasattr(msg, "content") else str(msg)
                })
        else:
            # Fallback format
            if isinstance(response, list):
                for msg in response:
                    if isinstance(msg, dict) and "content" in msg:
                        chat_history.append(msg)
                    else:
                        chat_history.append({
                            "role": "assistant",
                            "content": str(msg)
                        })
            else:
                chat_history.append({
                    "role": "assistant",
                    "content": str(response)
                })
                
        return chat_history
    
    def _get_schema_description(self, db_id: str) -> str:
        """Get the schema description for a database."""
        try:
            # Try to fetch schema using the SchemaRetrieverAgent
            schema_result = self.agents["schema"]._get_schema_info(self.db_path, db_id)
            return schema_result
        except Exception as e:
            # Fallback to a basic description if schema retrieval fails
            return f"Schema for database {db_id}. Please check the database structure."
