import os
import sys
import json
import time
from pathlib import Path

# Add the parent directory to the path to import the module
sys.path.append(str(Path(__file__).parent.parent))

# Import the BirdSQLOrchestrator class
from autogen_bird_sql import BirdSQLOrchestrator

def main():
    """
    Demonstrate the multi-agent text-to-SQL system with real-world questions.
    """
    # Path to the database
    db_path = "databases"
    
    # Ensure database directory exists
    os.makedirs(db_path, exist_ok=True)
    
    # Create or update the sample database
    create_sample_database(os.path.join(db_path, "world_1.sqlite"), clean=True)
    
    # Initialize the orchestrator with the database path
    print("Initializing BirdSQL Orchestrator...")
    orchestrator = BirdSQLOrchestrator(db_path=db_path)
    
    # Example questions demonstrating different query patterns
    questions = [
        # Simple lookup query
        "What is the population of China?",
        
        # Aggregation query
        "What is the total population of countries in Asia?",
        
        # Ranking query
        "Which are the top 5 most populous countries?",
        
        # Comparison query
        "What is the population difference between China and the United States?",
        
        # More complex filtering
        "List all countries with population over 200 million that are not in Asia",
        
        # Calculation query
        "What percentage of the world's population lives in India?",
        
        # Join query (if the sample DB supported it)
        "Which cities in Japan have a population over 1 million?"
    ]
    
    # Process each question and measure performance
    for i, question in enumerate(questions):
        # Add separator between questions
        if i > 0:
            print("\n" + "="*80 + "\n")
            
        # Include database ID in the question
        full_question = f"Using database world_1, {question}"
        
        # Print the question
        print(f"Question {i+1}: {question}")
        
        # Time the processing
        start_time = time.time()
        
        try:
            # Process the question
            result = orchestrator.process_question(full_question)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Display SQL and results
            print(f"\nGenerated SQL ({process_time:.2f} seconds):")
            print(f"  {result['sql']}")
            
            # Format results based on validation status
            if result["validation_status"] == "PASS":
                print("\nExecution Results:")
                execution_results = result.get("execution_results", {})
                
                if isinstance(execution_results, dict) and "results" in execution_results:
                    results = execution_results["results"]
                    
                    if results and len(results) > 0:
                        # Format specific result types
                        if isinstance(results[0], dict):
                            _format_dict_results(results)
                        else:
                            # Handle non-dict results
                            for item in results:
                                print(f"  {item}")
                    else:
                        print("  No results found.")
                else:
                    print(f"  {execution_results}")
            else:
                print(f"\nError: {result.get('error_message', 'Unknown error')}")
                
            # Show a validation note
            if result.get("validation_status"):
                validation = "✓ PASSED" if result["validation_status"] == "PASS" else "✗ FAILED"
                print(f"\nValidation: {validation}")
                
        except Exception as e:
            # Handle any exceptions
            process_time = time.time() - start_time
            print(f"\nError processing question ({process_time:.2f} seconds):")
            print(f"  {str(e)}")

def _format_dict_results(results):
    """Format dictionary results for better readability."""
    # For population difference type results
    if len(results) == 1 and "population_difference" in results[0]:
        result = results[0]
        print(f"  Population difference: {result.get('population_difference', 'N/A'):,}")
        print(f"  China population: {result.get('china_population', 'N/A'):,}")
        print(f"  US population: {result.get('us_population', 'N/A'):,}")
        return

    # For country ranking results
    if len(results) > 1 and all(isinstance(r, dict) and "name" in r and "population" in r for r in results):
        print("  Top countries by population:")
        for i, country in enumerate(results, 1):
            population = country.get('population')
            if isinstance(population, (int, float)):
                print(f"  {i}. {country['name']}: {population:,}")
            else:
                print(f"  {i}. {country['name']}: {population}")
        return

    # General case - just print the key-value pairs
    if len(results) == 1:
        # Single result
        for key, value in results[0].items():
            if isinstance(value, (int, float)):
                print(f"  {key}: {value:,}")
            else:
                print(f"  {key}: {value}")
    else:
        # Multiple results
        for i, item in enumerate(results, 1):
            print(f"  Result {i}:")
            for key, value in item.items():
                if isinstance(value, (int, float)):
                    print(f"    {key}: {value:,}")
                else:
                    print(f"    {key}: {value}")

def create_sample_database(db_path, clean=True):
    """
    Create a sample SQLite database with realistic country data.
    
    Args:
        db_path: Path to the database file
        clean: If True, delete existing data before inserting
    """
    import sqlite3
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    
    # Drop table if cleaning is requested
    if clean:
        conn.execute("DROP TABLE IF EXISTS country")
        conn.execute("DROP TABLE IF EXISTS continent")
    
    # Create continent table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS continent (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE
    )
    """)
    
    # Create country table with continent reference
    conn.execute("""
    CREATE TABLE IF NOT EXISTS country (
        id INTEGER PRIMARY KEY,
        name TEXT,
        continent_id INTEGER,
        population INTEGER,
        area_sq_km INTEGER,
        gdp_usd BIGINT,
        FOREIGN KEY (continent_id) REFERENCES continent (id)
    )
    """)
    
    # Insert continent data
    continents = [
        (1, "Asia"),
        (2, "Africa"),
        (3, "Europe"),
        (4, "North America"),
        (5, "South America"),
        (6, "Oceania"),
        (7, "Antarctica")
    ]
    
    conn.executemany("INSERT OR REPLACE INTO continent (id, name) VALUES (?, ?)", continents)
    
    # Insert expanded country data with continent IDs and additional metrics
    countries = [
        ("China", 1, 1400000000, 9596960, 14722730697600),
        ("India", 1, 1380000000, 3287263, 2946060440000),
        ("United States", 4, 331000000, 9525067, 20940000000000),
        ("Indonesia", 1, 273500000, 1904569, 1058424580000),
        ("Pakistan", 1, 220800000, 881912, 304400000000),
        ("Brazil", 5, 212600000, 8515767, 1830000000000),
        ("Nigeria", 2, 206100000, 923768, 432000000000),
        ("Bangladesh", 1, 164700000, 147570, 324000000000),
        ("Russia", 3, 144500000, 17098242, 1640000000000),
        ("Mexico", 4, 128900000, 1964375, 1150000000000),
        ("Japan", 1, 126500000, 377930, 5100000000000),
        ("Philippines", 1, 109600000, 342353, 370000000000),
        ("Egypt", 2, 102300000, 1001449, 302000000000),
        ("Ethiopia", 2, 114900000, 1104300, 93600000000),
        ("Vietnam", 1, 97300000, 331212, 260000000000),
        ("Germany", 3, 83700000, 357022, 3800000000000),
        ("Turkey", 1, 84300000, 783562, 720000000000),
        ("Iran", 1, 83900000, 1648195, 454000000000),
        ("United Kingdom", 3, 67800000, 242900, 2710000000000),
        ("France", 3, 65200000, 551695, 2630000000000),
        ("Italy", 3, 60400000, 301340, 1890000000000),
        ("South Africa", 2, 59300000, 1221037, 351000000000),
        ("Tanzania", 2, 59700000, 945087, 62000000000),
        ("Myanmar", 1, 54400000, 676578, 76000000000),
        ("South Korea", 1, 51700000, 100210, 1630000000000),
        ("Colombia", 5, 50300000, 1141748, 314000000000),
        ("Kenya", 2, 53500000, 580367, 98000000000),
        ("Spain", 3, 47300000, 505992, 1280000000000),
        ("Argentina", 5, 45100000, 2780400, 383000000000),
        ("Algeria", 2, 43800000, 2381741, 167000000000),
        ("Sudan", 2, 43800000, 1886068, 30000000000),
        ("Ukraine", 3, 44100000, 603500, 153000000000),
        ("Iraq", 1, 40200000, 438317, 192000000000),
        ("Afghanistan", 1, 38900000, 652230, 19000000000),
        ("Poland", 3, 37800000, 312696, 592000000000),
        ("Canada", 4, 37700000, 9984670, 1640000000000),
        ("Morocco", 2, 36900000, 446550, 120000000000),
        ("Saudi Arabia", 1, 34800000, 2149690, 700000000000),
        ("Uzbekistan", 1, 33500000, 447400, 60000000000),
        ("Peru", 5, 32900000, 1285216, 225000000000),
        ("Malaysia", 1, 32300000, 330803, 364000000000),
        ("Angola", 2, 32800000, 1246700, 89000000000),
        ("Mozambique", 2, 31200000, 801590, 15000000000),
        ("Ghana", 2, 31000000, 238535, 67000000000),
        ("Yemen", 1, 29800000, 527968, 23000000000),
        ("Nepal", 1, 29100000, 147181, 30000000000),
        ("Venezuela", 5, 28400000, 916445, 76000000000),
        ("Australia", 6, 25400000, 7692024, 1390000000000),
        ("North Korea", 1, 25700000, 120538, 28000000000),
        ("Taiwan", 1, 23800000, 35980, 589000000000)
    ]
    
    conn.executemany(
        "INSERT OR REPLACE INTO country (name, continent_id, population, area_sq_km, gdp_usd) VALUES (?, ?, ?, ?, ?)",
        countries
    )
    
    conn.commit()
    conn.close()
    
    print(f"Sample database created at {db_path}")
    return db_path

if __name__ == "__main__":
    main() 