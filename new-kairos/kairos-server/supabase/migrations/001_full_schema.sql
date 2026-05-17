-- =============================================================================
-- Kairos — full schema migration
-- Run once in the Supabase SQL Editor (after setup.sql which created profiles,
-- cv_data, and the cv-uploads bucket).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Extend profiles with new columns
-- ---------------------------------------------------------------------------
ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS skills          text[]  NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS experience_summary text,
  ADD COLUMN IF NOT EXISTS references_list text[]  NOT NULL DEFAULT '{}';

-- FK to auth.users (safe to add even if rows exist; user_id values must already
-- match auth.users since profiles were always created via the API with real UUIDs)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'profiles_user_id_fkey'
      AND table_name = 'profiles'
  ) THEN
    ALTER TABLE public.profiles
      ADD CONSTRAINT profiles_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. cvs — one row per uploaded PDF file
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.cvs (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name         text        NOT NULL,
  storage_path text        NOT NULL,
  size_bytes   bigint      NOT NULL DEFAULT 0,
  is_default   boolean     NOT NULL DEFAULT false,
  uploaded_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS cvs_user_id_idx ON public.cvs (user_id);

ALTER TABLE public.cvs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users read own cvs"
  ON public.cvs FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "users insert own cvs"
  ON public.cvs FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users update own cvs"
  ON public.cvs FOR UPDATE TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "users delete own cvs"
  ON public.cvs FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 3. matches — job match records (populated by background matching pipeline)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.matches (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  company    text        NOT NULL,
  role       text        NOT NULL,
  location   text        NOT NULL DEFAULT '',
  posted_at  timestamptz NOT NULL DEFAULT now(),
  score      integer     NOT NULL DEFAULT 0 CHECK (score BETWEEN 0 AND 100),
  skills     text[]      NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS matches_user_id_idx   ON public.matches (user_id);
CREATE INDEX IF NOT EXISTS matches_score_idx      ON public.matches (user_id, score DESC);
CREATE INDEX IF NOT EXISTS matches_posted_at_idx  ON public.matches (user_id, posted_at DESC);

ALTER TABLE public.matches ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users read own matches"
  ON public.matches FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 4. saved_matches — bookmark state
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.saved_matches (
  user_id  uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  match_id uuid        NOT NULL REFERENCES public.matches(id) ON DELETE CASCADE,
  saved_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, match_id)
);

ALTER TABLE public.saved_matches ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users manage own saved matches"
  ON public.saved_matches FOR ALL TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 5. applications — apply records
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.applications (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  match_id   uuid        NOT NULL REFERENCES public.matches(id) ON DELETE CASCADE,
  applied_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, match_id)
);

CREATE INDEX IF NOT EXISTS applications_user_id_idx ON public.applications (user_id);

ALTER TABLE public.applications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users manage own applications"
  ON public.applications FOR ALL TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 6. user_settings — notification preferences
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_settings (
  user_id              uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name         text,
  notification_channel text NOT NULL DEFAULT 'email'
    CHECK (notification_channel IN ('whatsapp','telegram','slack','discord','email')),
  updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION public.set_user_settings_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER user_settings_updated_at
  BEFORE UPDATE ON public.user_settings
  FOR EACH ROW EXECUTE FUNCTION public.set_user_settings_updated_at();

ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users manage own settings"
  ON public.user_settings FOR ALL TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 7. job_preferences — saved job tag selections
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.job_preferences (
  user_id    uuid    PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  tags       text[]  NOT NULL DEFAULT '{}',
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION public.set_job_preferences_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER job_preferences_updated_at
  BEFORE UPDATE ON public.job_preferences
  FOR EACH ROW EXECUTE FUNCTION public.set_job_preferences_updated_at();

ALTER TABLE public.job_preferences ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users manage own job preferences"
  ON public.job_preferences FOR ALL TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 8. connectors_status — which connectors a user has connected
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.connectors_status (
  user_id      uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  connector_id text NOT NULL,
  connected_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, connector_id)
);

ALTER TABLE public.connectors_status ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users manage own connectors"
  ON public.connectors_status FOR ALL TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 9. active_channel — user's chosen notification channel connector
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.active_channel (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  channel text NOT NULL
);

ALTER TABLE public.active_channel ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users manage own active channel"
  ON public.active_channel FOR ALL TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 10. activities — event log / timeline
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.activities (
  id       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id  uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  icon_key text        NOT NULL CHECK (icon_key IN ('match','apply','save','cv','agent')),
  label    text        NOT NULL,
  at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS activities_user_id_at_idx ON public.activities (user_id, at DESC);

ALTER TABLE public.activities ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users read own activities"
  ON public.activities FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "users insert own activities"
  ON public.activities FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);
