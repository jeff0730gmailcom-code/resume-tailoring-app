import { useEffect, useState } from "react";
import { ApiError, deleteAdminUser, fetchAdminUsers, updateAdminUser } from "../services/api";
import type { AdminUserRow, UserPublic } from "../types";
import { formatWhen } from "./ActivityHistory";

interface UsersPageProps {
  currentUser: UserPublic;
  onViewActivity: (userId: number) => void;
}

function statusLabel(user: AdminUserRow): { text: string; className: string } {
  if (!user.is_active) return { text: "Blocked", className: "bg-red-100 text-red-800" };
  if (user.role === "admin") return { text: "Administrator", className: "bg-navy text-gold-200" };
  if (!user.is_approved) return { text: "Waiting", className: "bg-amber-100 text-amber-900" };
  return { text: "Allowed", className: "bg-green-100 text-green-800" };
}

export default function UsersPage({ currentUser, onViewActivity }: UsersPageProps) {
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  async function load() {
    try {
      setUsers(await fetchAdminUsers());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load members.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function patch(userId: number, body: { is_approved?: boolean; is_active?: boolean }) {
    setBusyId(userId);
    setError(null);
    try {
      const updated = await updateAdminUser(userId, body);
      setUsers((current) => current.map((row) => (row.id === updated.id ? updated : row)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update that member.");
    } finally {
      setBusyId(null);
    }
  }

  async function remove(user: AdminUserRow) {
    if (!window.confirm(`Delete ${user.name}? Their activity history will be removed.`)) return;
    setBusyId(user.id);
    setError(null);
    try {
      await deleteAdminUser(user.id);
      setUsers((current) => current.filter((row) => row.id !== user.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete that member.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="font-sans text-[11px] font-semibold tracking-[0.35em] text-navy-600">HOUSE LEDGER</p>
        <h2 className="font-display text-3xl text-navy">Members</h2>
        <p className="mt-1 font-suit text-lg italic text-navy-700">
          Allow new registrations, open a member&apos;s activity, or delete an account.
        </p>
      </div>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}

      {users.length === 0 && !error ? (
        <p className="font-sans text-sm text-navy-600">No members yet.</p>
      ) : null}

      {users.map((user) => {
        const badge = statusLabel(user);
        const isSelf = user.id === currentUser.id;
        const canAllow = !user.is_approved || !user.is_active;
        return (
          <article key={user.id} className="border border-navy/10 bg-white/90 p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-display text-2xl text-navy">{user.name}</h3>
                <p className="font-sans text-sm text-navy-600">{user.email}</p>
                <p className="mt-1 font-sans text-xs text-navy-600">Joined {formatWhen(user.created_at)}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${badge.className}`}>{badge.text}</span>
                <span className="font-sans text-xs text-navy-600">
                  {user.resume_count} tailor job{user.resume_count === 1 ? "" : "s"}
                </span>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onViewActivity(user.id)}
                className="border border-navy px-3 py-1.5 font-sans text-xs font-semibold tracking-wide text-navy"
              >
                View activity
              </button>
              {canAllow && !isSelf ? (
                <button
                  type="button"
                  disabled={busyId === user.id}
                  onClick={() => void patch(user.id, { is_approved: true, is_active: true })}
                  className="bg-navy px-3 py-1.5 font-sans text-xs font-semibold tracking-wide text-gold-200 disabled:opacity-50"
                >
                  Allow
                </button>
              ) : null}
              {user.is_active && !isSelf ? (
                <button
                  type="button"
                  disabled={busyId === user.id}
                  onClick={() => void patch(user.id, { is_active: false })}
                  className="border border-red-700 px-3 py-1.5 font-sans text-xs font-semibold tracking-wide text-red-800 disabled:opacity-50"
                >
                  Block
                </button>
              ) : null}
              {!user.is_active && !isSelf ? (
                <button
                  type="button"
                  disabled={busyId === user.id}
                  onClick={() => void patch(user.id, { is_active: true, is_approved: true })}
                  className="border border-navy px-3 py-1.5 font-sans text-xs font-semibold tracking-wide text-navy disabled:opacity-50"
                >
                  Unblock
                </button>
              ) : null}
              {!isSelf ? (
                <button
                  type="button"
                  disabled={busyId === user.id}
                  onClick={() => void remove(user)}
                  className="border border-red-700 bg-red-50 px-3 py-1.5 font-sans text-xs font-semibold tracking-wide text-red-800 disabled:opacity-50"
                >
                  Delete
                </button>
              ) : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}
