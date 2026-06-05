import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { secureFetch } from "@/utils/secureFetch";
import { useAuth } from "../../state/auth";
import { isAdmin, isStaff } from "../../types/user";
import NotFound from "../NotFound";

type InfractionSummary = {
  id: number;
  user_id: number;
  username: string;
  game_id: number;
  game_link: string | null;
  censored_message: string;
  severity: string;
  status: string;
  created_at: string;
  matched_term_count: number;
};

type InfractionDetail = InfractionSummary & {
  original_message: string;
  matched_terms: string[];
  moderator_notes: string | null;
};

type UserHistory = {
  id: number;
  username: string;
  role: string;
  is_banned: boolean;
  ban_expires_at: string | null;
  pending_infractions: number;
  total_infractions: number;
  is_muted: boolean;
};

type StaffMember = {
  id: number;
  username: string;
  role: string;
};

type StaffActionRecord = {
  id: number;
  actor_username: string;
  target_username: string | null;
  action_type: string;
  reason: string | null;
  created_at: string;
};

async function readError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (typeof data?.detail?.message === "string") return data.detail.message;
  } catch {
    // ignore
  }
  return "Request failed";
}

export default function AdminPage() {
  const { user, loading: authLoading } = useAuth();
  const [queue, setQueue] = useState<InfractionSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<InfractionDetail | null>(null);
  const [userHistory, setUserHistory] = useState<UserHistory | null>(null);
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [auditLog, setAuditLog] = useState<StaffActionRecord[]>([]);
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [muteHours, setMuteHours] = useState(24);
  const [tempBanDays, setTempBanDays] = useState(3);
  const [permBan, setPermBan] = useState(true);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [dataLoading, setDataLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);

  const loadQueue = useCallback(async () => {
    const res = await secureFetch("/api/moderation/queue");
    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) throw new Error(await readError(res));
    setQueue(await res.json());
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (!user || !isStaff(user)) {
      setDataLoading(false);
      return;
    }

    (async () => {
      try {
        await loadQueue();
        if (isAdmin(user)) {
          const staffRes = await secureFetch("/api/admin/staff");
          if (staffRes.ok) setStaff(await staffRes.json());
          const auditRes = await secureFetch("/api/admin/audit-log");
          if (auditRes.ok) setAuditLog(await auditRes.json());
        }
      } catch (err) {
        setStatusMessage(err instanceof Error ? err.message : "Failed to load moderation data");
      } finally {
        setDataLoading(false);
      }
    })();
  }, [user, authLoading, loadQueue]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setUserHistory(null);
      return;
    }

    (async () => {
      const detailRes = await secureFetch(`/api/moderation/infractions/${selectedId}`);
      if (!detailRes.ok) {
        setStatusMessage(await readError(detailRes));
        return;
      }
      const detailData: InfractionDetail = await detailRes.json();
      setDetail(detailData);

      const historyRes = await secureFetch(`/api/moderation/users/${detailData.user_id}/history`);
      if (historyRes.ok) {
        setUserHistory(await historyRes.json());
      }
    })();
  }, [selectedId]);

  const actionPayload = () => ({ reason: reason.trim(), notes: notes.trim() || undefined });

  const runAction = async (path: string, body?: Record<string, unknown>) => {
    setStatusMessage(null);
    const res = await secureFetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? actionPayload()),
    });
    if (!res.ok) {
      setStatusMessage(await readError(res));
      return;
    }
    setReason("");
    setNotes("");
    setSelectedId(null);
    await loadQueue();
    setStatusMessage("Action completed.");
  };

  if (!authLoading && (!user || !isStaff(user) || forbidden)) {
    return <NotFound />;
  }

  if (authLoading || dataLoading) {
    return (
      <div className="pt-24 px-8 text-white">
        <p className="text-slate-300">Loading moderation tools...</p>
      </div>
    );
  }

  return (
    <div className="pt-20 px-6 pb-10 text-white max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Moderation</h1>
        <Link to="/" className="text-sm text-blue-400 hover:underline">
          Back to game
        </Link>
      </div>

      {statusMessage && (
        <div className="mb-4 rounded border border-slate-600 bg-slate-800 px-4 py-2 text-sm text-slate-200">
          {statusMessage}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="rounded-lg border border-slate-700 bg-slate-900/80 p-4">
          <h2 className="text-lg font-semibold mb-3">Review queue</h2>
          {queue.length === 0 ? (
            <p className="text-slate-400 text-sm">No pending infractions.</p>
          ) : (
            <ul className="space-y-2">
              {queue.map((item) => (
                <li key={item.id}>
                  <button
                    onClick={() => setSelectedId(item.id)}
                    className={`w-full text-left rounded border px-3 py-2 text-sm transition-colors ${
                      selectedId === item.id
                        ? "border-blue-500 bg-slate-800"
                        : "border-slate-700 hover:border-slate-500"
                    }`}
                  >
                    <div className="font-medium">{item.username}</div>
                    <div className="text-slate-300 truncate">{item.censored_message}</div>
                    <div className="text-xs text-slate-500 mt-1">
                      {new Date(item.created_at).toLocaleString()} · {item.matched_term_count} match(es)
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-lg border border-slate-700 bg-slate-900/80 p-4">
          <h2 className="text-lg font-semibold mb-3">Infraction detail</h2>
          {!detail ? (
            <p className="text-slate-400 text-sm">Select an infraction from the queue.</p>
          ) : (
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-slate-400">User:</span> {detail.username}
              </div>
              {userHistory && (
                <div className="text-slate-400">
                  History: {userHistory.total_infractions} total · {userHistory.pending_infractions} pending
                  {userHistory.is_muted ? " · muted" : ""}
                  {userHistory.is_banned ? " · banned" : ""}
                </div>
              )}
              {detail.game_link && (
                <div>
                  <span className="text-slate-400">Game:</span>{" "}
                  <Link to={`/games/${detail.game_link}`} className="text-blue-400 hover:underline">
                    {detail.game_link}
                  </Link>
                </div>
              )}
              <div>
                <div className="text-slate-400 mb-1">Original (staff only)</div>
                <div className="rounded bg-slate-950 border border-slate-700 p-2 break-words">
                  {detail.original_message}
                </div>
              </div>
              <div>
                <div className="text-slate-400 mb-1">Shown in chat</div>
                <div className="rounded bg-slate-950 border border-slate-700 p-2 break-words">
                  {detail.censored_message}
                </div>
              </div>

              <label className="block">
                <span className="text-slate-400">Reason</span>
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  className="mt-1 w-full rounded bg-slate-800 border border-slate-600 px-2 py-1"
                />
              </label>
              <label className="block">
                <span className="text-slate-400">Notes (optional)</span>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="mt-1 w-full rounded bg-slate-800 border border-slate-600 px-2 py-1"
                  rows={2}
                />
              </label>

              <div className="flex flex-wrap gap-2 pt-2">
                <button
                  onClick={() => runAction(`/api/moderation/infractions/${detail.id}/dismiss`)}
                  className="rounded bg-slate-700 px-3 py-1 hover:bg-slate-600"
                >
                  Dismiss
                </button>
                <button
                  onClick={() => runAction(`/api/moderation/users/${detail.user_id}/warn`)}
                  className="rounded bg-yellow-700 px-3 py-1 hover:bg-yellow-600"
                >
                  Warn
                </button>
                <button
                  onClick={() =>
                    runAction(`/api/moderation/users/${detail.user_id}/mute`, {
                      ...actionPayload(),
                      hours: muteHours,
                    })
                  }
                  className="rounded bg-orange-700 px-3 py-1 hover:bg-orange-600"
                >
                  Mute {muteHours}h
                </button>
                <button
                  onClick={() =>
                    runAction(`/api/moderation/users/${detail.user_id}/temp-ban`, {
                      ...actionPayload(),
                      days: tempBanDays,
                    })
                  }
                  className="rounded bg-red-800 px-3 py-1 hover:bg-red-700"
                >
                  Temp ban {tempBanDays}d
                </button>
                {isAdmin(user) && (
                  <>
                    <button
                      onClick={() =>
                        runAction(`/api/admin/users/${detail.user_id}/ban`, {
                          ...actionPayload(),
                          permanent: permBan,
                          days: permBan ? undefined : tempBanDays,
                        })
                      }
                      className="rounded bg-red-950 px-3 py-1 hover:bg-red-900 border border-red-700"
                    >
                      {permBan ? "Permanent ban" : `Ban ${tempBanDays}d`}
                    </button>
                    {userHistory?.is_banned && (
                      <button
                        onClick={() => runAction(`/api/admin/users/${detail.user_id}/unban`)}
                        className="rounded bg-green-800 px-3 py-1 hover:bg-green-700"
                      >
                        Unban
                      </button>
                    )}
                  </>
                )}
              </div>

              <div className="flex flex-wrap gap-4 pt-2">
                <label className="text-xs text-slate-400">
                  Mute hours
                  <input
                    type="number"
                    min={1}
                    max={72}
                    value={muteHours}
                    onChange={(e) => setMuteHours(Number(e.target.value))}
                    className="ml-2 w-16 rounded bg-slate-800 border border-slate-600 px-1"
                  />
                </label>
                <label className="text-xs text-slate-400">
                  Temp ban days
                  <input
                    type="number"
                    min={1}
                    max={7}
                    value={tempBanDays}
                    onChange={(e) => setTempBanDays(Number(e.target.value))}
                    className="ml-2 w-16 rounded bg-slate-800 border border-slate-600 px-1"
                  />
                </label>
                {isAdmin(user) && (
                  <label className="text-xs text-slate-400 flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={permBan}
                      onChange={(e) => setPermBan(e.target.checked)}
                    />
                    Permanent ban (admin)
                  </label>
                )}
              </div>
            </div>
          )}
        </section>
      </div>

      {isAdmin(user) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <section className="rounded-lg border border-slate-700 bg-slate-900/80 p-4">
            <h2 className="text-lg font-semibold mb-3">Staff</h2>
            <ul className="space-y-1 text-sm">
              {staff.map((member) => (
                <li key={member.id} className="flex justify-between border-b border-slate-800 py-1">
                  <span>{member.username}</span>
                  <span className="text-slate-400 capitalize">{member.role}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-lg border border-slate-700 bg-slate-900/80 p-4">
            <h2 className="text-lg font-semibold mb-3">Recent audit log</h2>
            <ul className="space-y-2 text-xs max-h-64 overflow-y-auto">
              {auditLog.map((entry) => (
                <li key={entry.id} className="border-b border-slate-800 pb-2">
                  <div>
                    <span className="text-slate-300">{entry.actor_username}</span> ·{" "}
                    <span className="text-blue-300">{entry.action_type}</span>
                    {entry.target_username ? ` → ${entry.target_username}` : ""}
                  </div>
                  <div className="text-slate-500">{entry.reason}</div>
                  <div className="text-slate-600">{new Date(entry.created_at).toLocaleString()}</div>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
