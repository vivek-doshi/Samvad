# Pydantic models matching DB tables
# Note 1: This file is reserved for Pydantic BaseModel classes that mirror the
# SQLite tables defined in backend/db/schema.sql. These models serve as typed
# data transfer objects (DTOs) throughout the application.
#
# Note 2: Example model for the 'users' table:
#
#   from pydantic import BaseModel
#   from datetime import datetime
#   from typing import Optional
#
#   class User(BaseModel):
#       user_id: str
#       username: str
#       display_name: str
#       role: str = "user"
#       is_active: bool = True
#       created_at: datetime
#       last_login_at: Optional[datetime] = None
#
# Note 3: Pydantic models validate that data read from SQLite has the expected
# types. For example, if 'is_active' comes back as an integer (0/1) from SQLite,
# you can add a @field_validator to convert it to a boolean automatically.
#
# Note 4: Currently, DBClient.fetchone() returns plain dicts and callers access
# fields with dict["key"] syntax. Moving to typed Pydantic models would give
# IDE autocomplete support and catch field name typos at development time.
