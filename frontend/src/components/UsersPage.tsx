import { useEffect, useState } from "react";
import { ApiError, deleteAdminUser, fetchAdminUsers, updateAdminUser } from "../services/api";
import type { AdminUserRow, ResumeTemplateInfo, UserPublic } from "../types";
import { formatWhen } from "./ActivityHistory";
import Modal from "./Modal";

interface UsersPageProps {
  currentUser: UserPublic;
  onViewActivity: (userId: number) => void;
}

function statusLabel(user: AdminUserRow): { text: string; className: string } {
  if (!user.is_active) return { text: "Blocked", className: "bg-red-50 text-red-700" };
  if (user.role === "admin") return { text: "Administrator", className: "bg-brand-50 text-brand-600" };
  if (!user.is_approved) return { text: "Waiting", className: "bg-amber-50 text-amber-800" };
  return { text: "Allowed", className: "bg-emerald-50 text-emerald-800" };
}

function MemberTemplatesPreview({ templates }: { templates: ResumeTemplateInfo[] }) {
  const [selectedSlug, setSelectedSlug] = useState(templates[0]?.slug ?? null);
  const [lightbox, setLightbox] = useState<ResumeTemplateInfo | null>(null);
  const selected = templates.find((t) => t.slug === selectedSlug) ?? templates[0] ?? null;

  return (
    <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(180px,260px)]">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
        {templates.map((template) => {
          const isSelected = template.slug === selected?.slug;
          return (
            <button
              key={template.slug}
              type="button"
              onClick={() => setSelectedSlug(template.slug)}
              className={`overflow-hidden rounded-lg border text-left ${
                isSelected ? "border-indigo-500 ring-2 ring-indigo-200" : "border-slate-200"
              }`}
            >
              <div className="aspect-[3/4] bg-slate-100">
                <img
                  src={template.thumbnailUrl}
                  alt={template.name}
                  className="h-full w-full object-cover object-top"
                  loading="lazy"
                />
              </div>
              <div className="p-2">
                <p className="truncate text-xs font-medium text-slate-800">{template.name}</p>
                <p className="mt-0.5 text-[10px] text-slate-500">
                  {template.isBuiltin ? "Built-in" : "Uploaded"}
                  {template.isDefault ? " · Default" : ""}
                </p>
              </div>
            </button>
          );
        })}
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Preview</p>
        {selected ? (
          <button type="button" onClick={() => setLightbox(selected)} className="w-full text-left">
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
              <img
                src={selected.thumbnailUrl}
                alt={`${selected.name} preview`}
                className="mx-auto max-h-80 w-full object-contain object-top"
              />
            </div>
            <p className="mt-2 text-xs font-semibold text-slate-900">{selected.name}</p>
            <p className="text-[11px] text-indigo-600">Click to enlarge</p>
          </button>
        ) : null}
      </div>

      {lightbox ? (
        <Modal onClose={() => setLightbox(null)}>
          <img
            src={lightbox.thumbnailUrl}
            alt={`${lightbox.name} resume template preview`}
            className="max-h-[85vh] max-w-[90vw] rounded-lg object-contain shadow-2xl"
          />
        </Modal>
      ) : null}
    </div>
  );
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
        <h2 className="text-3xl font-bold tracking-tight text-slate-900">Members</h2>
        <p className="mt-1 text-sm text-slate-500">
          Allow new registrations, open a member&apos;s applications, or delete an account.
        </p>
      </div>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}

      {users.length === 0 && !error ? (
        <p className="text-sm text-slate-500">No members yet.</p>
      ) : null}

      {users.map((user) => {
        const badge = statusLabel(user);
        const isSelf = user.id === currentUser.id;
        const canAllow = !user.is_approved || !user.is_active;
        return (
          <article key={user.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-slate-900">{user.name}</h3>
                <p className="text-sm text-slate-500">{user.email}</p>
                <p className="mt-1 text-xs text-slate-400">Joined {formatWhen(user.created_at)}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${badge.className}`}>{badge.text}</span>
                <span className="text-xs text-slate-500">
                  {user.resume_count} application{user.resume_count === 1 ? "" : "s"}
                </span>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onViewActivity(user.id)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                View applications
              </button>
              {canAllow && !isSelf ? (
                <button
                  type="button"
                  disabled={busyId === user.id}
                  onClick={() => void patch(user.id, { is_approved: true, is_active: true })}
                  className="rounded-lg bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-600 disabled:opacity-50"
                >
                  Allow
                </button>
              ) : null}
              {user.is_active && !isSelf ? (
                <button
                  type="button"
                  disabled={busyId === user.id}
                  onClick={() => void patch(user.id, { is_active: false })}
                  className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                >
                  Block
                </button>
              ) : null}
              {!user.is_active && !isSelf ? (
                <button
                  type="button"
                  disabled={busyId === user.id}
                  onClick={() => void patch(user.id, { is_active: true, is_approved: true })}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  Unblock
                </button>
              ) : null}
              {!isSelf ? (
                <button
                  type="button"
                  disabled={busyId === user.id}
                  onClick={() => void remove(user)}
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 disabled:opacity-50"
                >
                  Delete
                </button>
              ) : null}
            </div>

            <div className="mt-5 border-t border-slate-100 pt-4">
              <h4 className="text-sm font-semibold text-slate-800">
                Templates ({user.templates?.length ?? 0})
              </h4>
              {(user.templates?.length ?? 0) === 0 ? (
                <p className="mt-1 text-xs text-slate-500">No templates uploaded yet.</p>
              ) : (
                <MemberTemplatesPreview templates={user.templates ?? []} />
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}
