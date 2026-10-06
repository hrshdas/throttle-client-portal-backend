-- Throttle Database Setup Script
-- Run as: psql -U postgres < scripts/setup_db.sql

-- Create the application user
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'throttle') THEN
    CREATE USER throttle WITH PASSWORD 'throttle123';
  END IF;
END
$$;

-- Create the database
SELECT 'CREATE DATABASE throttle OWNER throttle'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'throttle')\gexec

GRANT ALL PRIVILEGES ON DATABASE throttle TO throttle;

-- Allow throttle user to create schemas in the throttle database
\c throttle
GRANT ALL ON SCHEMA public TO throttle;
