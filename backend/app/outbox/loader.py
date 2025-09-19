"""
Outbox handlers auto-discovery module.

This module provides functionality to automatically discover and load
event handlers from the /app/handlers directory. Handlers using the
@outbox_handler decorator will be automatically registered with the
OutboxRegistry during application startup.
"""

import os
import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_handlers():
    """
    Auto-discovery and loading of all handlers in /app/handlers.
    
    This function scans the handlers directory and imports all Python modules,
    which triggers the registration of any decorated handler functions.
    Handlers must use the @outbox_handler decorator to be registered.
    
    The function will attempt to load all .py files in the handlers directory,
    logging success and failure cases for debugging purposes.
    
    Example directory structure:
        app/
          handlers/
            __init__.py
            user_handlers.py      # Contains @outbox_handler decorated functions
            payment_handlers.py   # Contains @outbox_handler decorated functions
            order_handlers.py     # Contains @outbox_handler decorated functions
    
    Raises:
        ImportError: If a handler module cannot be imported
    """
    handlers_dir = Path(__file__).parent.parent / "handlers"
    
    if not handlers_dir.exists():
        logger.warning("Handlers directory not found at: %s", handlers_dir)
        logger.info("Creating handlers directory for future use")
        try:
            handlers_dir.mkdir(parents=True, exist_ok=True)
            # Create __init__.py file
            init_file = handlers_dir / "__init__.py"
            init_file.write_text("# Event handlers module\n")
            logger.info("Created handlers directory and __init__.py")
        except Exception as e:
            logger.error("Failed to create handlers directory: %s", str(e))
        return
    
    logger.info("Starting handler auto-discovery in: %s", handlers_dir)
    
    # Load all .py files in the handlers directory
    loaded_count = 0
    failed_count = 0
    
    for file_path in handlers_dir.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
            
        # Convert to module path: app.handlers.payment_handlers
        module_name = f"app.handlers.{file_path.stem}"
        
        try:
            logger.debug("Attempting to load module: %s", module_name)
            importlib.import_module(module_name)
            logger.info("Successfully loaded handlers from: %s", module_name)
            loaded_count += 1
        except ImportError as e:
            logger.error("Import error loading %s: %s", module_name, str(e))
            failed_count += 1
        except Exception as e:
            logger.error("Unexpected error loading %s: %s", module_name, str(e), exc_info=True)
            failed_count += 1
    
    logger.info("Handler loading completed: %d loaded, %d failed", loaded_count, failed_count)


def reload_handlers():
    """
    Reload all handler modules.
    
    This function can be used in development to reload handler modules
    without restarting the application. Useful for testing handler changes.
    
    Note: This will not unregister previously registered handlers,
    so use with caution in production environments.
    """
    handlers_dir = Path(__file__).parent.parent / "handlers"
    
    if not handlers_dir.exists():
        logger.warning("Cannot reload: handlers directory not found")
        return
    
    logger.info("Reloading all handler modules")
    
    for file_path in handlers_dir.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
            
        module_name = f"app.handlers.{file_path.stem}"
        
        try:
            if module_name in os.sys.modules:
                logger.debug("Reloading module: %s", module_name)
                importlib.reload(os.sys.modules[module_name])
            else:
                logger.debug("Loading new module: %s", module_name)
                importlib.import_module(module_name)
            logger.info("Successfully reloaded: %s", module_name)
        except Exception as e:
            logger.error("Failed to reload %s: %s", module_name, str(e), exc_info=True)
    
    logger.info("Handler reload completed")