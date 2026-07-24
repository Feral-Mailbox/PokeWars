import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../state/auth';
import { secureFetch } from '@/utils/secureFetch';
import type { User } from '../types/user';
import { ProfileCard, normalizeProfileView, type ProfileViewModel } from './ProfileCard';
import { ProfileAccountSettings } from './ProfileAccountSettings';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; profile: ProfileViewModel; isOwn: boolean };

export default function PlayerProfilePage() {
  const { trainerId = '' } = useParams<{ trainerId: string }>();
  const { user, setUser } = useAuth();
  const [state, setState] = useState<LoadState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setState({ status: 'loading' });
      const normalized = trainerId.trim().toUpperCase();
      if (!normalized) {
        setState({ status: 'error', message: 'Player not found.' });
        return;
      }

      try {
        const res = await secureFetch(`/api/players/${encodeURIComponent(normalized)}`);
        if (!res) {
          if (!cancelled) {
            setState({ status: 'error', message: 'Could not load player profile.' });
          }
          return;
        }
        if (res.status === 404) {
          if (!cancelled) {
            setState({ status: 'error', message: 'Player not found.' });
          }
          return;
        }
        if (!res.ok) {
          if (!cancelled) {
            setState({ status: 'error', message: 'Could not load player profile.' });
          }
          return;
        }

        const data = normalizeProfileView(await res.json());
        let profile = data;
        let isOwn = Boolean(user?.trainer_id && user.trainer_id.toUpperCase() === normalized);

        if (isOwn) {
          try {
            const meRes = await secureFetch('/api/me');
            if (meRes?.ok) {
              const me = (await meRes.json()) as User;
              if (!cancelled) {
                setUser(me);
              }
              profile = normalizeProfileView({
                ...data,
                ...me,
                email: me.email,
              });
              isOwn = true;
            } else if (user) {
              profile = normalizeProfileView({ ...data, email: user.email });
            }
          } catch {
            if (user) {
              profile = normalizeProfileView({ ...data, email: user.email });
            }
          }
        }

        if (!cancelled) {
          setState({ status: 'ready', profile, isOwn });
        }
      } catch {
        if (!cancelled) {
          setState({ status: 'error', message: 'Could not load player profile.' });
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [trainerId, user?.trainer_id, setUser]);

  const handleUserUpdated = (updated: User) => {
    setUser(updated);
    setState((prev) => {
      if (prev.status !== 'ready') return prev;
      return {
        ...prev,
        profile: normalizeProfileView({
          ...prev.profile,
          ...updated,
          email: updated.email,
        }),
      };
    });
  };

  if (state.status === 'loading') {
    return (
      <div className="mx-auto max-w-2xl px-4 pt-24 pb-12 text-left text-gray-400">
        Loading player…
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="mx-auto max-w-2xl px-4 pt-24 pb-12 text-left text-white">
        <h1 className="text-3xl font-bold">Player not found</h1>
        <p className="mt-3 text-gray-300">{state.message}</p>
        <Link to="/" className="mt-6 inline-block text-blue-400 hover:text-blue-300">
          Back to home
        </Link>
      </div>
    );
  }

  return (
    <ProfileCard profile={state.profile} showEmail={state.isOwn}>
      {state.isOwn && state.profile.email ? (
        <ProfileAccountSettings
          key={state.profile.email}
          email={state.profile.email}
          onUserUpdated={handleUserUpdated}
        />
      ) : null}
    </ProfileCard>
  );
}
