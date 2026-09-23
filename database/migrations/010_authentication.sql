-- Authentication hardening and login audit.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS must_change_password boolean NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS failed_login_attempts integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS locked_until timestamptz,
    ADD COLUMN IF NOT EXISTS last_login_at timestamptz,
    ADD COLUMN IF NOT EXISTS password_changed_at timestamptz;

CREATE TABLE IF NOT EXISTS auth_login_events (
    id bigserial PRIMARY KEY,
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    email text NOT NULL,
    success boolean NOT NULL,
    reason text,
    ip_address inet,
    user_agent text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_login_events_email_time
    ON auth_login_events(email, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_auth_login_events_user_time
    ON auth_login_events(user_id, created_at DESC)
    WHERE user_id IS NOT NULL;
