# app/outbox/loader.py
import os
import importlib
from pathlib import Path

def load_handlers():
    """Auto-découverte et chargement de tous les handlers dans /app/handlers."""
    handlers_dir = Path(__file__).parent.parent / "handlers"
    
    if not handlers_dir.exists():
        print("Folder /app/handlers not found")
        return
    
    # Charger tous les fichiers .py dans le dossier handlers
    for file_path in handlers_dir.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
            
        # Convertir en module path: app.handlers.payment_handlers
        module_name = f"app.handlers.{file_path.stem}"
        
        try:
            importlib.import_module(module_name)
            print(f"Loaded handlers from {module_name}")
        except Exception as e:
            print(f"Failed to load {module_name}: {e}")