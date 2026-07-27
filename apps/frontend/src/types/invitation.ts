export type InvitationStatus =
  | 'pending'
  | 'accepted'
  | 'declined'
  | 'cancelled'
  | 'expired';

export type GameInvitation = {
  id: number;
  game_id: number;
  game_name: string;
  game_link: string;
  gamemode: string;
  inviter_id: number;
  inviter_username: string;
  invitee_id: number;
  invitee_username: string;
  status: InvitationStatus;
  created_at: string;
  expires_at?: string | null;
  responded_at?: string | null;
};

export type InboxPayload = {
  invitations: GameInvitation[];
  pending_count: number;
};

export type InvitationWsEvent = {
  event: 'invitation';
  action: 'created' | 'accepted' | 'declined' | 'cancelled' | 'expired';
  invitation: GameInvitation;
};

export type PlayerSearchHit = {
  id: number;
  trainer_id: string;
  username: string;
  avatar: string;
  elo_conquest: number;
  elo_war: number;
  role: string;
};
