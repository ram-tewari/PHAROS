-- Create alembic_version table with correct column size
-- Run this in NeonDB SQL Editor BEFORE deploying

-- Create the table with 64-character column (instead of default 32)
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(64) NOT NULL PRIMARY KEY
);

-- Verify the table was created
SELECT column_name, data_type, character_maximum_length 
FROM information_schema.columns 
WHERE table_name = 'alembic_version' AND column_name = 'version_num';
