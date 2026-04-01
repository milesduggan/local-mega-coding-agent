"""
Model Lifecycle Manager for llama-cpp models.

Provides centralized loading/unloading with idle detection and optional auto-unload.
Addresses the constraint that llama-cpp-python may not fully release memory on
Python object deletion - we use gc.collect() and optional manual gc as mitigations.
"""

import gc
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

# Add project root to path for config import
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))
sys.path.insert(0, _PROJECT_ROOT)

from scripts.config import MODEL_IDLE_TIMEOUT_MINUTES, AUTO_UNLOAD_ENABLED

log = logging.getLogger(__name__)


class ModelType(Enum):
    """Single model type — Qwen3 handles all roles."""
    MAIN = "main"


@dataclass
class ModelInfo:
    """Metadata and state for a managed model."""
    model_type: ModelType
    model_path: str
    config: Dict[str, Any]
    loader: Callable[[], Any]  # Function to load the model
    instance: Optional[Any] = None
    loaded_at: Optional[float] = None
    last_access: Optional[float] = None


class ModelManager:
    """
    Singleton manager for LLM model lifecycle.

    Thread-safe. Supports lazy loading, explicit unloading, and auto-unload.

    Features:
    - Lazy loading: Models are only loaded when first accessed
    - Access tracking: Timestamps updated on each get_model() call
    - Manual unload: Free memory explicitly via unload_model()
    - Auto-unload: Background thread unloads idle models (configurable)
    - Status reporting: Get detailed status of all models
    """

    _instance: Optional["ModelManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ModelManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._models: Dict[ModelType, ModelInfo] = {}
        self._model_lock = threading.Lock()

        # Configuration
        self._idle_timeout_minutes = MODEL_IDLE_TIMEOUT_MINUTES
        self._auto_unload_enabled = AUTO_UNLOAD_ENABLED

        # Background thread for auto-unload
        self._shutdown_event = threading.Event()
        self._idle_checker_thread: Optional[threading.Thread] = None

        if self._auto_unload_enabled and self._idle_timeout_minutes > 0:
            self._idle_checker_thread = threading.Thread(
                target=self._idle_check_loop,
                daemon=True,
                name="ModelIdleChecker"
            )
            self._idle_checker_thread.start()
            log.info(
                f"ModelManager: auto-unload enabled, "
                f"idle timeout={self._idle_timeout_minutes}min"
            )
        else:
            log.info("ModelManager: auto-unload disabled")

        self._initialized = True

    def register_model(
        self,
        model_type: ModelType,
        model_path: str,
        config: Dict[str, Any],
        loader: Callable[[], Any]
    ) -> None:
        """
        Register a model's configuration and loader function.

        Does not load the model - it will be loaded lazily on first access.

        Args:
            model_type: Type of model (e.g. ModelType.MAIN)
            model_path: Path to the model file
            config: Configuration dict (n_ctx, n_threads, etc.)
            loader: Callable that returns a loaded model instance
        """
        with self._model_lock:
            if model_type in self._models and self._models[model_type].instance is not None:
                log.warning(f"Re-registering {model_type.value} while loaded - unloading first")
                self._do_unload(model_type)

            self._models[model_type] = ModelInfo(
                model_type=model_type,
                model_path=model_path,
                config=config,
                loader=loader,
                instance=None,
                loaded_at=None,
                last_access=None
            )
            log.debug(f"Registered model: {model_type.value}")

    def get_model(self, model_type: ModelType) -> Any:
        """
        Get model instance, loading if necessary.

        Updates last_access timestamp on each call.

        Args:
            model_type: Type of model to get

        Returns:
            The model instance (Llama object)

        Raises:
            ValueError: If model type not registered
            FileNotFoundError: If model file doesn't exist
        """
        with self._model_lock:
            info = self._models.get(model_type)
            if info is None:
                raise ValueError(f"Model {model_type.value} not registered")

            now = time.time()

            if info.instance is None:
                log.info(f"Loading model: {model_type.value}")
                start = now

                if not os.path.exists(info.model_path):
                    raise FileNotFoundError(
                        f"Model not found: {info.model_path}\n"
                        f"Run setup_models.py to download."
                    )

                # Use the registered loader function
                info.instance = info.loader()
                info.loaded_at = now

                load_time = time.time() - start
                log.info(f"Model loaded: {model_type.value} ({load_time:.2f}s)")

            info.last_access = time.time()
            return info.instance

    def unload_model(self, model_type: ModelType) -> bool:
        """
        Unload a specific model to free memory.

        Args:
            model_type: Type of model to unload

        Returns:
            True if model was unloaded, False if not loaded
        """
        with self._model_lock:
            return self._do_unload(model_type)

    def _do_unload(self, model_type: ModelType) -> bool:
        """Internal unload - must be called with lock held."""
        info = self._models.get(model_type)
        if info is None or info.instance is None:
            return False

        log.info(f"Unloading model: {model_type.value}")

        # Clear any internal caches if available
        try:
            if hasattr(info.instance, 'reset'):
                info.instance.reset()
        except Exception as e:
            log.warning(f"Failed to reset model cache during unload: {type(e).__name__}: {e}")

        # Delete the instance
        instance = info.instance
        info.instance = None
        info.loaded_at = None
        info.last_access = None
        del instance

        # Aggressive garbage collection
        gc.collect()
        gc.collect()  # Second pass for cyclic refs

        log.info(f"Model unloaded: {model_type.value}")
        return True

    def unload_all(self) -> Dict[str, bool]:
        """
        Unload all models.

        Returns:
            Dict mapping model name to whether it was unloaded
        """
        results = {}
        with self._model_lock:
            for model_type in list(self._models.keys()):
                results[model_type.value] = self._do_unload(model_type)
        return results

    def get_status(self) -> Dict[str, Any]:
        """
        Get status of all models.

        Returns:
            Dict with model status and configuration info
        """
        with self._model_lock:
            now = time.time()
            status: Dict[str, Any] = {}

            for model_type, info in self._models.items():
                is_loaded = info.instance is not None
                idle_seconds = None
                if is_loaded and info.last_access:
                    idle_seconds = int(now - info.last_access)

                status[model_type.value] = {
                    "loaded": is_loaded,
                    "idle_seconds": idle_seconds,
                    "loaded_at": info.loaded_at,
                    "model_path": info.model_path,
                }

            status["config"] = {
                "idle_timeout_minutes": self._idle_timeout_minutes,
                "auto_unload_enabled": self._auto_unload_enabled,
            }

            return status

    def is_loaded(self, model_type: ModelType) -> bool:
        """Check if a specific model is currently loaded."""
        with self._model_lock:
            info = self._models.get(model_type)
            return info is not None and info.instance is not None

    def _idle_check_loop(self) -> None:
        """Background thread that checks for idle models and unloads them."""
        check_interval = 60  # Check every 60 seconds
        timeout_seconds = self._idle_timeout_minutes * 60

        log.debug(f"Idle checker started: interval={check_interval}s, timeout={timeout_seconds}s")

        while not self._shutdown_event.wait(check_interval):
            now = time.time()
            models_to_unload = []

            with self._model_lock:
                for model_type, info in self._models.items():
                    if info.instance is None or info.last_access is None:
                        continue

                    idle_time = now - info.last_access
                    if idle_time >= timeout_seconds:
                        log.info(
                            f"Auto-unloading {model_type.value} "
                            f"(idle for {idle_time/60:.1f} minutes)"
                        )
                        models_to_unload.append(model_type)

            # Unload outside the status check to avoid holding lock too long
            for model_type in models_to_unload:
                self.unload_model(model_type)

    def shutdown(self) -> None:
        """Clean shutdown - stop background thread and unload all models."""
        log.info("ModelManager shutting down")
        self._shutdown_event.set()
        if self._idle_checker_thread and self._idle_checker_thread.is_alive():
            self._idle_checker_thread.join(timeout=5)
        self.unload_all()


# Module-level singleton accessor
def get_manager() -> ModelManager:
    """Get the singleton ModelManager instance."""
    return ModelManager()
