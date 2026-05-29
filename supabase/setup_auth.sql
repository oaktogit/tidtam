-- ════════════════════════════════════════════════════════
-- Tidtam Auth Setup
-- รันใน Supabase Dashboard → SQL Editor → New query
-- ════════════════════════════════════════════════════════

-- 1) profiles table (extends auth.users)
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  full_name text,
  role text not null default 'user' check (role in ('admin', 'user')),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- 2) Auto-create profile when new user signs up
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email);
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- 3) Helper: check current user is admin (security definer = bypass RLS recursion)
create or replace function public.is_admin()
returns boolean
language sql
security definer set search_path = public
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role = 'admin'
  );
$$;

-- 4) RLS on profiles
alter table public.profiles enable row level security;

drop policy if exists "Read own profile"      on public.profiles;
drop policy if exists "Admins read profiles"  on public.profiles;
drop policy if exists "Admins update profiles" on public.profiles;
drop policy if exists "Admins delete profiles" on public.profiles;

create policy "Read own profile"
  on public.profiles for select
  using (auth.uid() = id);

create policy "Admins read profiles"
  on public.profiles for select
  using (public.is_admin());

create policy "Admins update profiles"
  on public.profiles for update
  using (public.is_admin());

create policy "Admins delete profiles"
  on public.profiles for delete
  using (public.is_admin());

-- 5) RLS on vehicles (require login to view)
alter table public.vehicles enable row level security;

drop policy if exists "Authenticated read vehicles" on public.vehicles;
create policy "Authenticated read vehicles"
  on public.vehicles for select
  using (auth.role() = 'authenticated');

-- 6) RLS on positions — same pattern, authenticated read only
alter table public.positions enable row level security;

drop policy if exists "Authenticated read positions" on public.positions;
create policy "Authenticated read positions"
  on public.positions for select
  using (auth.role() = 'authenticated');

-- ════════════════════════════════════════════════════════
-- หลังจากรัน SQL นี้แล้ว สร้าง admin คนแรก:
--   1. Authentication → Users → Add user → Create new user
--   2. ใส่ email + password (✅ Auto Confirm User)
--   3. รัน SQL นี้เพื่อ promote เป็น admin (เปลี่ยน email):
--      update public.profiles set role='admin' where email='YOUR_EMAIL';
-- ════════════════════════════════════════════════════════
