-- Channel-aware Publish context, review, clip selection, and upload options.
alter table public.publishing_jobs
  add column if not exists source_context jsonb,
  add column if not exists generated_clips jsonb,
  add column if not exists selected_clip_id text,
  add column if not exists upload_privacy_status text not null default 'private',
  add column if not exists upload_category_id text not null default '22',
  add column if not exists upload_tags jsonb not null default '[]'::jsonb;

alter table public.publishing_jobs drop constraint if exists publishing_jobs_status_check;
alter table public.publishing_jobs add constraint publishing_jobs_status_check check (
  status in (
    'discovering','waiting_for_source_approval','waiting_for_context_review','generating',
    'scoring','evaluating','revising','waiting_for_upload_approval','uploading',
    'complete','failed','cancelled'
  )
);
