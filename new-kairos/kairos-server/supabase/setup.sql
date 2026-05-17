-- =============================================================================
-- Kairos — simple Supabase setup
-- Run this entire file once in the Supabase SQL Editor
-- =============================================================================

-- ---------------------------------------------------------------------------
-- profiles: one row per user — stores onboarding info and portfolio projects
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.profiles (
  user_id    uuid        PRIMARY KEY,
  full_name  text,
  email      text,
  phone      text,
  job_title  text,
  location   text,
  linkedin   text,
  github     text,
  portfolio  text,
  projects   jsonb       NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Keep updated_at current automatically
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER profiles_updated_at
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users read own profile"
  ON public.profiles FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "users insert own profile"
  ON public.profiles FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users update own profile"
  ON public.profiles FOR UPDATE TO authenticated
  USING (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- cv_data: one row per parsed CV per user
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.cv_data (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid        NOT NULL,
  storage_path  text        NOT NULL,
  structured_json jsonb     NOT NULL,
  model_used    text,
  parsed_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS cv_data_user_id_idx ON public.cv_data (user_id);

-- Only keep the most recent parse per user (optional, remove if you want history)
CREATE UNIQUE INDEX IF NOT EXISTS cv_data_user_id_unique ON public.cv_data (user_id);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- Authenticated users can only see / write their own data.
-- The FastAPI server uses the service_role key and bypasses RLS.
-- ---------------------------------------------------------------------------
ALTER TABLE public.cv_data ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users read own cv_data"
  ON public.cv_data FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "users insert own cv_data"
  ON public.cv_data FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users update own cv_data"
  ON public.cv_data FOR UPDATE TO authenticated
  USING (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Storage bucket: cv-uploads
-- Private, PDF only, 10 MB max per file
-- ---------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'cv-uploads',
  'cv-uploads',
  false,
  10485760,
  ARRAY['application/pdf']
)
ON CONFLICT (id) DO NOTHING;

-- Files must live under the owner's user_id folder:  {user_id}/filename.pdf
CREATE POLICY "users upload own cv"
  ON storage.objects FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'cv-uploads'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "users read own cv"
  ON storage.objects FOR SELECT TO authenticated
  USING (
    bucket_id = 'cv-uploads'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "users update own cv"
  ON storage.objects FOR UPDATE TO authenticated
  USING (
    bucket_id = 'cv-uploads'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );
