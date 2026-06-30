import { decode } from 'base64-arraybuffer';
import type { User } from '@supabase/supabase-js';

import { supabase } from '@/lib/supabase';
import type { Profile, ProfileUpdate } from '@/lib/types';

function profileFromUser(user: User): ProfileUpdate {
  return {
    avatar_url: typeof user.user_metadata.avatar_url === 'string' ? user.user_metadata.avatar_url : null,
    email: user.email ?? '',
    full_name: typeof user.user_metadata.full_name === 'string' ? user.user_metadata.full_name : '',
  };
}

export async function fetchProfile(userId: string) {
  const { data, error } = await supabase.from('profiles').select('*').eq('id', userId).maybeSingle();
  if (error) {
    throw error;
  }
  return data as Profile | null;
}

export async function ensureProfile(user: User) {
  const existing = await fetchProfile(user.id);
  if (existing) {
    return existing;
  }

  const { data, error } = await supabase
    .from('profiles')
    .upsert({ id: user.id, ...profileFromUser(user) })
    .select('*')
    .single();

  if (error) {
    throw error;
  }

  return data as Profile;
}

export async function updateProfileRow(userId: string, patch: ProfileUpdate) {
  return supabase
    .from('profiles')
    .update({ ...patch, updated_at: new Date().toISOString() })
    .eq('id', userId)
    .select('*')
    .single<Profile>();
}

// Uploads a picked image (base64) to the `avatars` bucket at <userId>/avatar.<ext>
// and returns a public URL. Cache-busted so the new photo shows immediately.
export async function uploadAvatar(userId: string, base64: string, ext: string) {
  const path = `${userId}/avatar.${ext}`;
  const contentType = ext === 'png' ? 'image/png' : 'image/jpeg';

  const { error } = await supabase.storage
    .from('avatars')
    .upload(path, decode(base64), { contentType, upsert: true });
  if (error) throw error;

  const { data } = supabase.storage.from('avatars').getPublicUrl(path);
  return `${data.publicUrl}?v=${Date.now()}`;
}
