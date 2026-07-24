import type { UserRole } from '../types/user';

export type ProfileViewModel = {
  trainer_id: string;
  username: string;
  avatar: string;
  elo_conquest: number;
  elo_war: number;
  currency: number;
  role: UserRole | string;
  email?: string | null;
};

const DEFAULT_ELO = 1000;

/** Normalize API/auth payloads so profile Elo always renders a number. */
export function normalizeProfileView(
  raw: Partial<ProfileViewModel> & {
    elo?: number | null;
    elo_conquest?: number | null;
    elo_war?: number | null;
  },
): ProfileViewModel {
  const legacy = raw.elo;
  const conquest = raw.elo_conquest ?? legacy ?? DEFAULT_ELO;
  const war = raw.elo_war ?? legacy ?? DEFAULT_ELO;
  return {
    trainer_id: String(raw.trainer_id ?? ''),
    username: String(raw.username ?? ''),
    avatar: String(raw.avatar ?? 'default.png'),
    elo_conquest: Number.isFinite(Number(conquest)) ? Number(conquest) : DEFAULT_ELO,
    elo_war: Number.isFinite(Number(war)) ? Number(war) : DEFAULT_ELO,
    currency: Number.isFinite(Number(raw.currency)) ? Number(raw.currency) : 0,
    role: (raw.role as UserRole | string) ?? 'user',
    email: raw.email ?? null,
  };
}

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
  const view = normalizeProfileView(profile);

  return (
    <div className="mx-auto max-w-2xl px-4 pt-20 pb-12 text-left text-white">
      <div className="flex items-center gap-5">
        <AvatarMark username={view.username} avatar={view.avatar} />
        <div>
          <h1 className="text-3xl font-bold">{view.username}</h1>
          <p className="mt-1 text-sm text-gray-400">{roleLabel(String(view.role))}</p>
        </div>
      </div>

      <dl className="mt-8 grid gap-3 rounded-lg border border-gray-700 bg-gray-800/80 p-5 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-gray-400">Conquest Elo</dt>
          <dd className="mt-1 text-lg font-semibold text-white">{view.elo_conquest}</dd>
        </div>
        <div>
          <dt className="text-gray-400">War Elo</dt>
          <dd className="mt-1 text-lg font-semibold text-white">{view.elo_war}</dd>
        </div>
        <div>
          <dt className="text-gray-400">Currency</dt>
          <dd className="mt-1 text-lg font-semibold text-white">{view.currency}</dd>
        </div>
        {showEmail && view.email ? (
          <div>
            <dt className="text-gray-400">Email</dt>
            <dd className="mt-1 break-all text-white">{view.email}</dd>
          </div>
        ) : null}
        <div>
          <dt className="text-gray-400">Role</dt>
          <dd className="mt-1 capitalize text-white">{view.role}</dd>
        </div>
        <div>
          <dt className="text-gray-400">Trainer ID</dt>
          <dd className="mt-1 font-mono tracking-wide text-white">{view.trainer_id}</dd>
        </div>
      </dl>
    </div>
  );
}
