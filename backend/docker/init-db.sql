SELECT 'CREATE DATABASE eventdb_test'
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_database
    WHERE datname = 'eventdb_test'
)\gexec
