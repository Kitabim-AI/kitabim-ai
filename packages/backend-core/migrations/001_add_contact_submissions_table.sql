-- Migration: Add contact_submissions table
-- Created: 2026-02-23
-- Description: Adds table for storing contact form submissions from Join Us page

CREATE TABLE IF NOT EXISTS contact_submissions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    interest VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'new',
    admin_notes TEXT,
    reviewed_by VARCHAR(36),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT contact_submissions_interest_check CHECK (interest IN ('editor', 'developer', 'other')),
    CONSTRAINT contact_submissions_status_check CHECK (status IN ('new', 'reviewed', 'contacted', 'archived'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_contact_submissions_email ON contact_submissions(email);
CREATE INDEX IF NOT EXISTS idx_contact_submissions_status ON contact_submissions(status);
CREATE INDEX IF NOT EXISTS idx_contact_submissions_created_at ON contact_submissions(created_at);

-- Comment
COMMENT ON TABLE contact_submissions IS 'Contact form submissions from Join Us page';
COMMENT ON COLUMN contact_submissions.interest IS 'Type of interest: editor, developer, or other';
COMMENT ON COLUMN contact_submissions.status IS 'Submission status: new, reviewed, contacted, or archived';
