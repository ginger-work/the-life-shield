-- =============================================================================
-- The Life Shield - PostgreSQL Initialization
-- Creates database extensions and initial configuration
-- =============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable case-insensitive text search
CREATE EXTENSION IF NOT EXISTS "citext";

-- Enable encryption functions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enable full-text search
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create read-only reporting role (for analytics queries)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'lifeshield_readonly') THEN
        CREATE ROLE lifeshield_readonly NOLOGIN;
    END IF;
END
$$;

-- Grant read access to reporting role
GRANT CONNECT ON DATABASE lifeshield_db TO lifeshield_readonly;
GRANT USAGE ON SCHEMA public TO lifeshield_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO lifeshield_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO lifeshield_readonly;
