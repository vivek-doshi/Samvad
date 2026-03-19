# Pydantic settings — loads from .env + samvad.yaml
# Note 1: This file is reserved for Pydantic BaseSettings models that load
# application configuration from environment variables and the .env file.
# Pydantic BaseSettings (from pydantic-settings package) provides automatic
# type coercion, validation, and documentation of all required config values.
#
# Note 2: The recommended pattern is to define a Settings class here:
#
#   from pydantic_settings import BaseSettings
#   class Settings(BaseSettings):
#       secret_key: str             # reads SECRET_KEY env var
#       sqlite_path: str = "runtime/sqlite/samvad.db"
#       llama_server_host: str = "localhost"
#       class Config:
#           env_file = ".env"       # also loads from .env file
#
# Note 3: Currently, configuration is loaded directly via os.getenv() in each
# module. Centralising it here in a Settings class would make all config values
# discoverable in one place and allow validation at startup rather than at
# the first time a value is actually used.
