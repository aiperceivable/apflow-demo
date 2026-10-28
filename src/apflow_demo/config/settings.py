"""
Demo settings configuration
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class DemoSettings(BaseSettings):
    """Demo application settings"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # apflow configuration (passed through)
    apflow_api_protocol: str = os.getenv("APFLOW_API_PROTOCOL", "a2a")
    apflow_api_host: str = os.getenv("APFLOW_API_HOST", os.getenv("API_HOST", "0.0.0.0"))
    apflow_api_port: int = int(os.getenv("APFLOW_API_PORT", os.getenv("PORT", "8000")))
    apflow_base_url: Optional[str] = os.getenv("APFLOW_BASE_URL")
    
    # JWT (optional, defaults to demo secret key if not provided)
    apflow_jwt_secret_key: Optional[str] = os.getenv(
        "APFLOW_JWT_SECRET",
        "demo-secret-key-change-in-production"
    )
    apflow_jwt_algorithm: str = os.getenv("APFLOW_JWT_ALGORITHM", "HS256")
    
    # System routes and docs
    apflow_enable_system_routes: bool = os.getenv("APFLOW_ENABLE_SYSTEM_ROUTES", "true").lower() in ("true", "1", "yes")
    apflow_enable_docs: bool = os.getenv("APFLOW_ENABLE_DOCS", "true").lower() in ("true", "1", "yes")
    
    # CORS origins
    apflow_cors_origins: Optional[str] = os.getenv("APFLOW_CORS_ORIGINS")
    
    # Database URL
    database_url: Optional[str] = os.getenv("APFLOW_DATABASE_URL") or os.getenv("DATABASE_URL")

    def model_post_init(self, __context: object) -> None:
        """Initialize settings and ensure JWT secret is written to .env"""
        self._ensure_jwt_secret_in_env()

    def _ensure_jwt_secret_in_env(self) -> None:
        """Ensure APFLOW_JWT_SECRET is in .env file for apflow-demo command"""
        env_file = Path(".env")
        
        # Check if APFLOW_JWT_SECRET is already set from environment
        if os.getenv("APFLOW_JWT_SECRET"):
            return
        
        # Check if .env file exists and already has APFLOW_JWT_SECRET
        if env_file.exists():
            content = env_file.read_text()
            if "APFLOW_JWT_SECRET" in content:
                return
        
        # Write or append APFLOW_JWT_SECRET to .env
        if env_file.exists():
            with open(env_file, "a", encoding="utf-8") as f:
                f.write("\n# JWT Secret for apflow\n")
                f.write(f"APFLOW_JWT_SECRET={self.apflow_jwt_secret_key}\n")
        else:
            with open(env_file, "w", encoding="utf-8") as f:
                f.write("# JWT Secret for apflow\n")
                f.write(f"APFLOW_JWT_SECRET={self.apflow_jwt_secret_key}\n")
    
    def get_apflow_env(self) -> dict[str, str]:
        """Get environment variables for apflow"""
        env = {}
        if self.apflow_api_protocol:
            env["APFLOW_API_PROTOCOL"] = self.apflow_api_protocol
        if self.apflow_api_host:
            env["APFLOW_API_HOST"] = self.apflow_api_host
        if self.apflow_api_port:
            env["APFLOW_API_PORT"] = str(self.apflow_api_port)
        if self.apflow_base_url:
            env["APFLOW_BASE_URL"] = self.apflow_base_url
        if self.apflow_jwt_secret_key:
            env["APFLOW_JWT_SECRET"] = self.apflow_jwt_secret_key
        if self.apflow_jwt_algorithm:
            env["APFLOW_JWT_ALGORITHM"] = self.apflow_jwt_algorithm
        if self.apflow_enable_system_routes:
            env["APFLOW_ENABLE_SYSTEM_ROUTES"] = str(self.apflow_enable_system_routes).lower()
        if self.apflow_enable_docs:
            env["APFLOW_ENABLE_DOCS"] = str(self.apflow_enable_docs).lower()
        # Add CORS origins
        if self.apflow_cors_origins:
            env["APFLOW_CORS_ORIGINS"] = self.apflow_cors_origins
        # Add DATABASE_URL
        if self.database_url:
            env["DATABASE_URL"] = self.database_url
        return env


# Global settings instance
settings = DemoSettings()

