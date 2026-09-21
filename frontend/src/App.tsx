import { useCallback, useEffect, useMemo, useState } from "react";
import ActivityHistory from "./components/ActivityHistory";
import ApplicationAnswersPreview from "./components/ApplicationAnswersPreview";
import ApplicationQuestionsInput from "./components/ApplicationQuestionsInput";
import AuthPage from "./components/AuthPage";
import CoverLetterChoice from "./components/CoverLetterChoice";
import CoverLetterPreview from "./components/CoverLetterPreview";
import CvUpload from "./components/CvUpload";
import JobDescriptionInput from "./components/JobDescriptionInput";
import JobLinkHistory from "./components/JobLinkHistory";
import ResumePreview from "./components/ResumePreview";
import TailoringDetailsInput from "./components/TailoringDetailsInput";
import TemplateGallery from "./components/TemplateGallery";
import UsersPage from "./components/UsersPage";
import WaitingApproval from "./components/WaitingApproval";
import {
  ApiError,
  AUTH_EXPIRED_EVENT,
  checkApiHealth,
  clearAccessToken,
  fetchMe,
  getAccessToken,
  tailorResume,
  uploadCv,
} from "./services/api";
import type { CvVariant, UserPublic } from "./types";
import { userCanUseApp } from "./types";

function newLocalId(): string {
  return `cv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function generateButtonLabel(
  includeCoverLetter: boolean,
  hasQuestions: boolean,
  isGenerating: boolean,
  variantCount: number
): string {
  if (isGenerating) {
    if (variantCount > 1) return `Generating ${variantCount} resumes…`;
    if (includeCoverLetter && hasQuestions) return "Generating resume, cover letter & answers...";
    if (includeCoverLetter) return "Generating resume & cover letter...";
    if (hasQuestions) return "Generating resume & answers...";
    return "Generating...";
  }
  if (variantCount > 1) {
    if (includeCoverLetter && hasQuestions) return `Generate ${variantCount} resumes, letters & answers`;
    if (includeCoverLetter) return `Generate ${variantCount} resumes & cover letters`;
    if (hasQuestions) return `Generate ${variantCount} resumes & answers`;
    return `Generate ${variantCount} tailored resumes`;
  }
  if (includeCoverLetter && hasQuestions) return "Generate Resume, Cover Letter & Answers";
  if (includeCoverLetter) return "Generate Resume & Cover Letter";
  if (hasQuestions) return "Generate Resume & Answers";
  return "Generate Tailored Resume";
}

function App() {
  const [authReady, setAuthReady] = useState(false);
  const [user, setUser] = useState<UserPublic | null>(null);
  const [page, setPage] = useState<"work" | "users" | "activity" | "job-links">("work");
  const [activityUserId, setActivityUserId] = useState<number | null>(null);
  const [jobLinksScope, setJobLinksScope] = useState<"mine" | "all" | "member">("mine");
  const [jobLinksUserId, setJobLinksUserId] = useState<number | null>(null);
  const [jobLinksUserLabel, setJobLinksUserLabel] = useState("");
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking");

  const [variants, setVariants] = useState<CvVariant[]>([]);
  const [activeVariantId, setActiveVariantId] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [jobDescription, setJobDescription] = useState("");
  const [mainStack, setMainStack] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [jobLink, setJobLink] = useState("");
  const [includeCoverLetter, setIncludeCoverLetter] = useState(false);
  const [applicationQuestions, setApplicationQuestions] = useState<string[]>([]);
  const [attemptedGenerate, setAttemptedGenerate] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);

  const activeVariant = useMemo(
    () => variants.find((v) => v.localId === activeVariantId) ?? variants[0] ?? null,
    [variants, activeVariantId]
  );

  const anyGenerating = variants.some((v) => v.isGenerating);

  const resetWorkspace = useCallback(() => {
    setVariants([]);
    setActiveVariantId(null);
    setUploadError(null);
    setJobDescription("");
    setMainStack("");
    setCompanyName("");
    setJobLink("");
    setIncludeCoverLetter(false);
    setApplicationQuestions([]);
    setAttemptedGenerate(false);
    setBatchError(null);
  }, []);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      setAuthReady(true);
      return;
    }
    fetchMe()
      .then(setUser)
      .catch(() => {
        clearAccessToken();
        setUser(null);
      })
      .finally(() => setAuthReady(true));
  }, []);

  useEffect(() => {
    function onExpired() {
      setUser(null);
      resetWorkspace();
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, [resetWorkspace]);

  useEffect(() => {
    if (!user) return;
    checkApiHealth()
      .then(() => setApiStatus("online"))
      .catch(() => setApiStatus("offline"));
  }, [user]);

  const handleSignedIn = useCallback((nextUser: UserPublic) => {
    setUser(nextUser);
  }, []);

  function handleSignOut() {
    clearAccessToken();
    setUser(null);
    setPage("work");
    setActivityUserId(null);
    resetWorkspace();
  }

  function updateVariant(localId: string, patch: Partial<CvVariant>) {
    setVariants((current) => current.map((v) => (v.localId === localId ? { ...v, ...patch } : v)));
  }

  async function handleFilesSelected(files: File[]) {
    if (!files.length) return;
    setIsUploading(true);
    setUploadError(null);
    setBatchError(null);
    const inheritedTemplate =
      activeVariant?.templateSlug ?? variants.find((v) => v.templateSlug)?.templateSlug ?? null;
    const created: CvVariant[] = [];
    const errors: string[] = [];

    for (const file of files) {
      try {
        const uploaded = await uploadCv(file);
        created.push({
          localId: newLocalId(),
          cv: uploaded,
          templateSlug: inheritedTemplate,
          resume: null,
          coverLetter: null,
          applicationAnswers: [],
          generatedFilename: null,
          generateError: null,
          isGenerating: false,
          lastGenerateIncludedLetter: false,
          lastGenerateHadQuestions: false,
        });
      } catch (err) {
        errors.push(
          `${file.name}: ${err instanceof ApiError ? err.message : "Upload failed."}`
        );
      }
    }

    if (created.length) {
      setVariants((current) => [...current, ...created]);
      setActiveVariantId(created[created.length - 1].localId);
    }
    if (errors.length) {
      setUploadError(errors.join(" "));
    }
    setIsUploading(false);
  }

  function handleRemoveVariant(localId: string) {
    setVariants((current) => {
      const next = current.filter((v) => v.localId !== localId);
      setActiveVariantId((active) => {
        if (active !== localId) return active;
        return next[0]?.localId ?? null;
      });
      return next;
    });
  }

  async function tailorOneVariant(variant: CvVariant): Promise<void> {
    if (!variant.templateSlug) {
      updateVariant(variant.localId, {
        generateError: "Select a resume template for this CV.",
        isGenerating: false,
      });
      return;
    }
    updateVariant(variant.localId, {
      isGenerating: true,
      generateError: null,
      lastGenerateIncludedLetter: includeCoverLetter,
      lastGenerateHadQuestions: applicationQuestions.length > 0,
    });
    try {
      const result = await tailorResume(
        variant.cv.fileId,
        jobDescription,
        mainStack.trim(),
        companyName.trim(),
        jobLink.trim(),
        variant.templateSlug,
        includeCoverLetter,
        applicationQuestions
      );
      updateVariant(variant.localId, {
        resume: result.resume,
        coverLetter: result.coverLetter,
        applicationAnswers: result.applicationAnswers,
        generatedFilename: result.generatedFilename,
        isGenerating: false,
        generateError: null,
      });
    } catch (err) {
      updateVariant(variant.localId, {
        isGenerating: false,
        generateError:
          err instanceof ApiError ? err.message : "Failed to generate a tailored resume.",
      });
    }
  }

  async function handleGenerate() {
    setAttemptedGenerate(true);
    setBatchError(null);
    const jobOk =
      jobDescription.trim().length > 0 &&
      mainStack.trim().length > 0 &&
      companyName.trim().length > 0 &&
      (jobLink.trim().startsWith("http://") || jobLink.trim().startsWith("https://"));
    if (!jobOk || variants.length === 0) return;

    const ready = variants.filter((v) => v.templateSlug);
    if (ready.length === 0) return;

    setActiveVariantId(ready[0].localId);
    // Sequential to avoid hammering the AI endpoint with many parallel calls.
    for (const variant of ready) {
      await tailorOneVariant(variant);
    }
  }

  const readyCount = variants.filter((v) => v.templateSlug).length;
  const jobFieldsOk =
    jobDescription.trim().length > 0 &&
    mainStack.trim().length > 0 &&
    companyName.trim().length > 0 &&
    (jobLink.trim().startsWith("http://") || jobLink.trim().startsWith("https://"));

  const canGenerate =
    variants.length > 0 && readyCount > 0 && jobFieldsOk && !anyGenerating && !isUploading;

  const answersSectionNumber = includeCoverLetter ? 5 : 4;

  if (!authReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="text-sm text-slate-500">Loading...</p>
      </div>
    );
  }

  if (!user) {
    return <AuthPage onSignedIn={handleSignedIn} />;
  }

  if (!userCanUseApp(user)) {
    return <WaitingApproval name={user.name} onSignOut={handleSignOut} />;
  }

  const signedInUser = user;
  const isAdmin = signedInUser.role === "admin";
  const viewingOtherActivity = page === "activity" && activityUserId != null && activityUserId !== signedInUser.id;
  const viewingAdminJobLinks = page === "job-links" && jobLinksScope !== "mine";
  const isWorkPage = page === "work";
  const isActivityPage = page === "activity";
  const isJobLinksPage = page === "job-links";
  const useWorkShell = isWorkPage || isActivityPage || isJobLinksPage;
  const shellWidth = useWorkShell ? "max-w-none" : "max-w-7xl";

  function openMyActivity() {
    setActivityUserId(signedInUser.id);
    setPage("activity");
  }

  function openMemberActivity(userId: number) {
    setActivityUserId(userId);
    setPage("activity");
  }

  function openMyJobLinks() {
    setJobLinksScope("mine");
    setJobLinksUserId(null);
    setJobLinksUserLabel("");
    setPage("job-links");
  }

  function openAllJobLinks() {
    setJobLinksScope("all");
    setJobLinksUserId(null);
    setJobLinksUserLabel("");
    setPage("job-links");
  }

  function openMemberJobLinks(userId: number, userName: string) {
    setJobLinksScope("member");
    setJobLinksUserId(userId);
    setJobLinksUserLabel(userName);
    setPage("job-links");
  }

  const tabClass = (active: boolean) =>
    `rounded-lg px-3.5 py-2 text-sm font-medium ${
      active ? "border border-slate-200 bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:bg-white/80 hover:text-slate-800"
    }`;

  return (
    <div className={`bg-slate-50 ${isWorkPage ? "flex h-screen flex-col overflow-hidden" : "min-h-screen"}`}>
      <header className="shrink-0 border-b border-slate-200 bg-white">
        <div className={`mx-auto flex ${shellWidth} items-center justify-between px-4 py-3 lg:px-6`}>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brand">Resume Tailor</p>
            <h1 className="text-lg font-semibold text-slate-900">
              {page === "activity"
                ? "Applications"
                : page === "job-links"
                  ? jobLinksScope === "all"
                    ? "All job links"
                    : jobLinksScope === "member"
                      ? "Member job links"
                      : "Job links"
                  : page === "users"
                    ? "Members"
                    : "Create application"}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                apiStatus === "online"
                  ? "bg-emerald-50 text-emerald-700"
                  : apiStatus === "offline"
                    ? "bg-red-50 text-red-700"
                    : "bg-slate-100 text-slate-500"
              }`}
            >
              API {apiStatus}
            </span>
            <span className="hidden text-sm text-slate-600 sm:inline">{signedInUser.name}</span>
            <button
              type="button"
              onClick={handleSignOut}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <div
        className={`mx-auto flex min-h-0 w-full flex-1 flex-col ${shellWidth} ${
          useWorkShell ? "overflow-hidden px-4 pt-3 lg:px-6 lg:pt-4" : "px-4 py-6"
        }`}
      >
        <div className={`flex flex-wrap gap-2 ${useWorkShell ? "mb-3 shrink-0" : "mb-6"}`}>
          <button type="button" onClick={() => setPage("work")} className={tabClass(page === "work")}>
            Create application
          </button>
          <button type="button" onClick={openMyActivity} className={tabClass(page === "activity" && !viewingOtherActivity)}>
            Applications
          </button>
          <button type="button" onClick={openMyJobLinks} className={tabClass(page === "job-links" && !viewingAdminJobLinks)}>
            Job links
          </button>
          {isAdmin ? (
            <button
              type="button"
              onClick={() => setPage("users")}
              className={tabClass(page === "users" || viewingOtherActivity || viewingAdminJobLinks)}
            >
              Users
            </button>
          ) : null}
        </div>

      {page === "users" && isAdmin ? (
        <main>
          <UsersPage
            currentUser={signedInUser}
            onViewActivity={openMemberActivity}
            onViewJobLinks={openMemberJobLinks}
            onViewAllJobLinks={openAllJobLinks}
          />
        </main>
      ) : page === "activity" ? (
        <main className="min-h-0 flex-1 overflow-y-auto pb-4">
          {viewingOtherActivity ? (
            <button
              type="button"
              onClick={() => setPage("users")}
              className="mb-4 text-sm font-medium text-brand hover:underline"
            >
              Back to members
            </button>
          ) : null}
          <ActivityHistory currentUser={signedInUser} memberId={viewingOtherActivity ? activityUserId : null} />
        </main>
      ) : page === "job-links" ? (
        <main className="min-h-0 flex-1 overflow-y-auto pb-4">
          <JobLinkHistory
            scope={jobLinksScope}
            memberId={jobLinksScope === "member" ? jobLinksUserId : null}
            memberLabel={jobLinksUserLabel}
            onBack={viewingAdminJobLinks ? () => setPage("users") : undefined}
          />
        </main>
      ) : (
      <main className="flex min-h-0 flex-1 flex-col gap-4 pb-4 lg:grid lg:grid-cols-2 lg:gap-0 lg:overflow-hidden lg:pb-0">
        <div className="flex min-h-0 flex-col lg:overflow-hidden lg:border-r lg:border-slate-200 lg:pr-5">
          <div className="flex min-h-0 flex-1 flex-col gap-4 lg:overflow-y-auto lg:pb-3">
            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">1. Upload master CVs</h2>
              <p className="mb-3 mt-0.5 text-xs text-slate-500">
                One or more PDF/Word CVs for the same job. Each CV can use its own template; preview shows the selected CV.
              </p>
              <CvUpload
                multiple
                onFileSelected={(file) => void handleFilesSelected([file])}
                onFilesSelected={(files) => void handleFilesSelected(files)}
                isUploading={isUploading}
                error={uploadError}
                emptyLabel={variants.length ? "Add another master CV" : "Click to upload or drag and drop"}
              />
              {variants.length > 0 ? (
                <ul className="mt-3 flex flex-col gap-2">
                  {variants.map((variant, index) => {
                    const isActive = variant.localId === (activeVariant?.localId ?? "");
                    return (
                      <li key={variant.localId}>
                        <div
                          className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${
                            isActive ? "border-indigo-400 bg-indigo-50/60" : "border-slate-200 bg-white"
                          }`}
                        >
                          <button
                            type="button"
                            onClick={() => setActiveVariantId(variant.localId)}
                            className="min-w-0 flex-1 text-left"
                          >
                            <p className="truncate text-sm font-medium text-slate-800">
                              CV {index + 1}: {variant.cv.fileName}
                            </p>
                            <p className="truncate text-[11px] text-slate-500">
                              {variant.templateSlug
                                ? `Template: ${variant.templateSlug}`
                                : "No template selected"}
                              {variant.resume ? " · Ready" : ""}
                              {variant.isGenerating ? " · Generating…" : ""}
                              {variant.generateError ? " · Error" : ""}
                            </p>
                          </button>
                          <button
                            type="button"
                            disabled={anyGenerating || isUploading}
                            onClick={() => handleRemoveVariant(variant.localId)}
                            className="shrink-0 rounded px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-40"
                          >
                            Remove
                          </button>
                        </div>
                        {variant.generateError ? (
                          <p className="mt-1 px-1 text-xs text-red-600">{variant.generateError}</p>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              ) : null}
              {attemptedGenerate && variants.length === 0 ? (
                <p className="mt-2 text-xs text-red-600">Upload at least one master CV.</p>
              ) : null}
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">2. Job details</h2>
              <p className="mb-3 mt-0.5 text-xs text-slate-500">Shared across every master CV for this application.</p>
              <div className="flex flex-col gap-4">
                <JobDescriptionInput value={jobDescription} onChange={setJobDescription} />
                <TailoringDetailsInput
                  mainStack={mainStack}
                  onMainStackChange={setMainStack}
                  companyName={companyName}
                  onCompanyNameChange={setCompanyName}
                  jobLink={jobLink}
                  onJobLinkChange={setJobLink}
                  showValidation={attemptedGenerate}
                />
                <CoverLetterChoice
                  value={includeCoverLetter}
                  onChange={setIncludeCoverLetter}
                  disabled={anyGenerating || isUploading}
                />
                <ApplicationQuestionsInput
                  questions={applicationQuestions}
                  onChange={setApplicationQuestions}
                  disabled={anyGenerating || isUploading}
                />
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">3. Template for selected CV</h2>
              <p className="mb-3 mt-0.5 text-xs text-slate-500">
                {activeVariant
                  ? `Choose a template for “${activeVariant.cv.fileName}”. Switch CVs above to set each one.`
                  : "Upload a master CV first, then pick its template."}
              </p>
              {activeVariant ? (
                <TemplateGallery
                  key={activeVariant.localId}
                  selectedSlug={activeVariant.templateSlug}
                  onSelect={(slug) => updateVariant(activeVariant.localId, { templateSlug: slug })}
                  showValidation={attemptedGenerate}
                  disabled={anyGenerating || isUploading}
                  dense
                />
              ) : (
                <p className="text-sm text-slate-500">No CV selected.</p>
              )}
            </section>
          </div>

          <div className="sticky bottom-0 z-10 shrink-0 border-t border-slate-200 bg-slate-50/95 py-3 backdrop-blur lg:border-slate-200">
            <button
              type="button"
              disabled={!canGenerate}
              onClick={() => void handleGenerate()}
              className="w-full rounded-xl bg-brand px-4 py-3 font-semibold text-white shadow-sm transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {generateButtonLabel(
                includeCoverLetter,
                applicationQuestions.length > 0,
                anyGenerating,
                readyCount || 1
              )}
            </button>
            {batchError ? <p className="mt-2 text-sm text-red-600">{batchError}</p> : null}
            {attemptedGenerate && variants.length > 0 && readyCount === 0 ? (
              <p className="mt-2 text-sm text-red-600">Select a template for at least one CV.</p>
            ) : null}
          </div>
        </div>

        <div className="flex min-h-0 flex-col gap-4 lg:overflow-y-auto lg:pl-5 lg:pb-4">
          <section className="flex min-h-0 flex-1 flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm lg:min-h-[calc(100vh-11rem)]">
            <div className="mb-3 flex shrink-0 flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-slate-900">4. Preview &amp; download</h2>
            </div>
            {variants.length > 1 ? (
              <div className="mb-3 flex shrink-0 flex-wrap gap-1.5">
                {variants.map((variant, index) => {
                  const isActive = variant.localId === (activeVariant?.localId ?? "");
                  return (
                    <button
                      key={variant.localId}
                      type="button"
                      onClick={() => setActiveVariantId(variant.localId)}
                      className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                        isActive
                          ? "bg-slate-900 text-white"
                          : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      CV {index + 1}
                      {variant.resume ? "" : " · pending"}
                    </button>
                  );
                })}
              </div>
            ) : null}
            <div className="flex min-h-0 flex-1 flex-col">
              <ResumePreview
                resume={activeVariant?.resume ?? null}
                fileId={activeVariant?.cv.fileId ?? null}
                generatedFilename={activeVariant?.generatedFilename ?? null}
                fillHeight
              />
            </div>
          </section>

          <CoverLetterPreview
            includeCoverLetter={includeCoverLetter}
            coverLetter={activeVariant?.coverLetter ?? null}
            isGenerating={activeVariant?.isGenerating ?? false}
            hasResume={Boolean(activeVariant?.resume)}
            lastGenerateIncludedLetter={activeVariant?.lastGenerateIncludedLetter ?? false}
          />

          <ApplicationAnswersPreview
            sectionNumber={answersSectionNumber}
            questions={applicationQuestions}
            answers={activeVariant?.applicationAnswers ?? []}
            isGenerating={activeVariant?.isGenerating ?? false}
            hasResume={Boolean(activeVariant?.resume)}
            lastGenerateHadQuestions={activeVariant?.lastGenerateHadQuestions ?? false}
          />
        </div>
      </main>
      )}
      </div>
    </div>
  );
}

export default App;
