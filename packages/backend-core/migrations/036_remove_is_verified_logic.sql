-- Migration: Remove is_verified logic
-- Removes is_verified from pages table

ALTER TABLE pages DROP COLUMN IF EXISTS is_verified;
