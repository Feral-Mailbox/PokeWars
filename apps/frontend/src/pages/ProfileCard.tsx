import type { UserRole } from '../types/user';

export type ProfileViewModel = {
  trainer_id: string;
  username: string;
  avatar: string;
  elo: number;
  currency: number;
  role: UserRole | string;
  email?: string | null;
};

export function roleLabel(role: string): string {
  if (role === 'admin') return 'Admin';
  if (role === 'moderator') return 'Moderator';
  return 'Trainer';
}

export function AvatarMark({ username, avatar }: { username: string; avatar: string }) {
  const initial = (username.trim()[0] || '?').toUpperCase();
  const hasCustomAvatar = Boolean(avatar && avatar !== 'default.png');

  return (
    <div
      className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-full border border-gray-600 bg-gray-900 text-2xl font-semibold text-indigo-300"
      aria-hidden={!hasCustomAvatar}
    >
      {hasCustomAvatar ? (
        <img src={avatar} alt="" className="h-full w-full object-cover" />
      ) : (
        <span>{initial}</span>
      )}
    </div>
  );
}

type ProfileCardProps = {
  profile: ProfileViewModel;
  showEmail?: boolean;
};

export function ProfileCard({ profile, showEmail = false }: ProfileCardProps) {
  return (
    <div className="mx-auto max-w-2xl px-4 pt-20 pb-12 text-left text-white">
      <div className="flex items-center gap-5">
        <AvatarMark username={profile.username} avatar={profile.avatar} />
        <div>
          <h1 className="text-3xl font-bold">{profile.username}</h1>
          <p className="mt-1 text-sm text-gray-400">{roleLabel(String(profile.role))}</p>
        </div>
      </div>

      <dl className="mt-8 grid gap-3 rounded-lg border border-gray-700 bg-gray-800/80 p-5 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-gray-400">Elo</dt>
          <dd className="mt-1 text-lg font-semibold text-white">{profile.elo}</dd>
        </div>
        <div>
          <dt className="text-gray-400">Currency</dt>
          <dd className="mt-1 text-lg font-semibold text-white">{profile.currency}</dd>
        </div>
        {showEmail && profile.email ? (
          <div className="sm:col-span-2">
            <dt className="text-gray-400">Email</dt>
            <dd className="mt-1 break-all text-white">{profile.email}</dd>
          </div>
        ) : null}
        <div>
          <dt className="text-gray-400">Role</dt>
          <dd className="mt-1 capitalize text-white">{profile.role}</dd>
        </div>
        <div>
          <dt className="text-gray-400">Trainer ID</dt>
          <dd className="mt-1 font-mono tracking-wide text-white">{profile.trainer_id}</dd>
        </div>
      </dl>
    </div>
  );
}
