#!/usr/bin/env python3
"""
Development startup script for HAOS Orchestrator
Run with: python start_dev.py
"""

import os
import sys
from pathlib import Path

def main():
    # Get the directory where this script is located
    script_dir = Path(__file__).resolve().parent
    os.chdir(script_dir)
    
    print("Starting HAOS Orchestrator in development mode...")
    
    # Create data directories if they don't exist
    data_dirs = [
        "data/orchestrator",
        "data/orchestrator/logs",
        "data/orchestrator/config",
        "data/orchestrator/tokens",
    ]
    
    for dir_path in data_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    # Copy example config if not exists
    env_file = script_dir / ".env"
    env_example = script_dir / ".env.example"
    if not env_file.exists() and env_example.exists():
        import shutil
        shutil.copy(env_example, env_file)
        print("Created .env from .env.example")
    
    # Start the server
    print("\nServer running at: http://localhost:8000")
    print("Dashboard: http://localhost:8000/dashboard")
    print("Press Ctrl+C to stop\n")
    
    # Run uvicorn
    from uvicorn import run
    run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )

if __name__ == "__main__":
    main()
