import { useCallback, useEffect, useState } from "react";
import ActivityHistory from "./components/ActivityHistory";
import ApplicationAnswersPreview from "./components/ApplicationAnswersPreview";
import ApplicationQuestionsInput from "./components/ApplicationQuestionsInput";
import AuthPage from "./components/AuthPage";
import CoverLetterChoice from "./components/CoverLetterChoice";
import CoverLetterPreview from "./components/CoverLetterPreview";
import CvUpload from "./components/CvUpload";
import JobDescriptionInput from "./components/JobDescriptionInput";
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
import type { ApplicationAnswerItem, CoverLetterContent, TailoredResumeContent, UploadedCv, UserPublic } from "./types";
import { userCanUseApp } from "./types";

function generateButtonLabel(includeCoverLetter: boolean, hasQuestions: boolean, isGenerating: boolean): string {
  if (isGenerating) {
    if (includeCoverLetter && hasQuestions) return "Generating resume, cover letter & answers...";
    if (includeCoverLetter) return "Generating resume & cover letter...";
    if (hasQuestions) return "Generating resume & answers...";
    return "Generating...";
  }
  if (includeCoverLetter && hasQuestions) return "Generate Resume, Cover Letter & Answers";
  if (includeCoverLetter) return "Generate Resume & Cover Letter";
  if (hasQuestions) return "Generate Resume & Answers";
  return "Generate Tailored Resume";
}

function App() {
  const [authReady, setAuthReady] = useState(false);
  const [user, setUser] = useState<UserPublic | null>(null);
  const [page, setPage] = useState<"work" | "users" | "activity">("work");
  const [activityUserId, setActivityUserId] = useState<number | null>(null);
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking");

  const [cv, setCv] = useState<UploadedCv | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [jobDescription, setJobDescription] = useState("");
  const [mainStack, setMainStack] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [jobLink, setJobLink] = useState("");
  const [selectedTemplateSlug, setSelectedTemplateSlug] = useState<string | null>(null);
  const [includeCoverLetter, setIncludeCoverLetter] = useState(false);
  const [applicationQuestions, setApplicationQuestions] = useState<string[]>([]);
  const [attemptedGenerate, setAttemptedGenerate] = useState(false);

  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [resume, setResume] = useState<TailoredResumeContent | null>(null);
  const [coverLetter, setCoverLetter] = useState<CoverLetterContent | null>(null);
  const [applicationAnswers, setApplicationAnswers] = useState<ApplicationAnswerItem[]>([]);
  const [lastGenerateIncludedLetter, setLastGenerateIncludedLetter] = useState(false);
  const [lastGenerateHadQuestions, setLastGenerateHadQuestions] = useState(false);
  const [generatedFilename, setGeneratedFilename] = useState<string | null>(null);

  const resetWorkspace = useCallback(() => {
    setCv(null);
    setUploadError(null);
    setJobDescription("");
    setMainStack("");
    setCompanyName("");
    setJobLink("");
    setSelectedTemplateSlug(null);
    setIncludeCoverLetter(false);
    setApplicationQuestions([]);
    setAttemptedGenerate(false);
    setGenerateError(null);
    setResume(null);
    setCoverLetter(null);
    setApplicationAnswers([]);
    setLastGenerateIncludedLetter(false);
    setLastGenerateHadQuestions(false);
    setGeneratedFilename(null);
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

  async function handleFileSelected(file: File) {
    setIsUploading(true);
    setUploadError(null);
    setResume(null);
    setCoverLetter(null);
    setApplicationAnswers([]);
    setLastGenerateIncludedLetter(false);
    setLastGenerateHadQuestions(false);
    setGeneratedFilename(null);
    try {
      const uploaded = await uploadCv(file);
      setCv(uploaded);
    } catch (err) {
      setCv(null);
      setUploadError(err instanceof ApiError ? err.message : "Failed to upload CV. Please try again.");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleGenerate() {
    setAttemptedGenerate(true);
    if (!cv || !mainStack.trim() || !companyName.trim() || !jobLink.trim() || !selectedTemplateSlug) return;
    setIsGenerating(true);
    setGenerateError(null);
    setCoverLetter(null);
    setApplicationAnswers([]);
    setLastGenerateIncludedLetter(includeCoverLetter);
    setLastGenerateHadQuestions(applicationQuestions.length > 0);
    try {
      // ATS matching/scoring happens entirely on the backend (see
      // app/services/ats_scorer.py) and is intentionally never surfaced in
      // the UI - result.atsMatch is available in the API response for
      // backend/internal use but is deliberately not read here.
      const result = await tailorResume(
        cv.fileId,
        jobDescription,
        mainStack.trim(),
        companyName.trim(),
        jobLink.trim(),
        selectedTemplateSlug,
        includeCoverLetter,
        applicationQuestions
      );
      setResume(result.resume);
      setCoverLetter(result.coverLetter);
      setApplicationAnswers(result.applicationAnswers);
      setGeneratedFilename(result.generatedFilename);
    } catch (err) {
      setGenerateError(
        err instanceof ApiError ? err.message : "Failed to generate a tailored resume. Please try again."
      );
    } finally {
      setIsGenerating(false);
    }
  }

  const canGenerate =
    Boolean(cv) &&
    jobDescription.trim().length > 0 &&
    mainStack.trim().length > 0 &&
    companyName.trim().length > 0 &&
    (jobLink.trim().startsWith("http://") || jobLink.trim().startsWith("https://")) &&
    Boolean(selectedTemplateSlug) &&
    !isGenerating &&
    !isUploading;

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
  const shellWidth = page === "users" || page === "activity" ? "max-w-7xl" : "max-w-4xl";

  function openMyActivity() {
    setActivityUserId(signedInUser.id);
    setPage("activity");
  }

  function openMemberActivity(userId: number) {
    setActivityUserId(userId);
    setPage("activity");
  }

  const tabClass = (active: boolean) =>
    `rounded-lg px-3.5 py-2 text-sm font-medium ${
      active ? "border border-slate-200 bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:bg-white/80 hover:text-slate-800"
    }`;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className={`mx-auto flex ${shellWidth} items-center justify-between px-4 py-3`}>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brand">Resume Tailor</p>
            <h1 className="text-lg font-semibold text-slate-900">
              {page === "activity" ? "Applications" : page === "users" ? "Members" : "Create application"}
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

      <div className={`mx-auto ${shellWidth} px-4 py-6`}>
        <div className="mb-6 flex flex-wrap gap-2">
          <button type="button" onClick={() => setPage("work")} className={tabClass(page === "work")}>
            Create application
          </button>
          <button type="button" onClick={openMyActivity} className={tabClass(page === "activity" && !viewingOtherActivity)}>
            Applications
          </button>
          {isAdmin ? (
            <button type="button" onClick={() => setPage("users")} className={tabClass(page === "users" || viewingOtherActivity)}>
              Users
            </button>
          ) : null}
        </div>

      {page === "users" && isAdmin ? (
        <main>
          <UsersPage currentUser={signedInUser} onViewActivity={openMemberActivity} />
        </main>
      ) : page === "activity" ? (
        <main>
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
      ) : (
      <main className="flex flex-col gap-6">
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">1. Upload master CV</h2>
          <p className="mb-4 mt-1 text-sm text-slate-500">PDF or Word file. This is the source of identity facts such as titles and employers.</p>
          <CvUpload onFileSelected={handleFileSelected} fileName={cv?.fileName} isUploading={isUploading} error={uploadError} />
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">2. Paste job description</h2>
          <p className="mb-4 mt-1 text-sm text-slate-500">Add the posting, stack, company, and a template.</p>
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
          <div className="flex flex-col gap-2">
            <span className="font-medium text-slate-700">
              Your resume templates <span className="text-red-500">*</span>
            </span>
            <p className="text-sm text-slate-500">
              Pick one of your templates, or upload a sample CV (PDF/DOCX). You only see templates you own.
            </p>
            <TemplateGallery
              selectedSlug={selectedTemplateSlug}
              onSelect={setSelectedTemplateSlug}
              showValidation={attemptedGenerate}
            />
          </div>
          <CoverLetterChoice
            value={includeCoverLetter}
            onChange={setIncludeCoverLetter}
            disabled={isGenerating || isUploading}
          />
          <ApplicationQuestionsInput
            questions={applicationQuestions}
            onChange={setApplicationQuestions}
            disabled={isGenerating || isUploading}
          />
          </div>
        </section>

        <section className="flex flex-col gap-2">
          <button
            disabled={!canGenerate}
            onClick={handleGenerate}
            className="w-full rounded-xl bg-brand px-4 py-3 font-semibold text-white shadow-sm transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {generateButtonLabel(includeCoverLetter, applicationQuestions.length > 0, isGenerating)}
          </button>
          {generateError && <p className="text-sm text-red-600">{generateError}</p>}
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-base font-semibold text-slate-900">3. Preview &amp; download</h2>
          <ResumePreview
            resume={resume}
            fileId={cv?.fileId ?? null}
            generatedFilename={generatedFilename}
          />
        </section>

        <CoverLetterPreview
          includeCoverLetter={includeCoverLetter}
          coverLetter={coverLetter}
          isGenerating={isGenerating}
          hasResume={Boolean(resume)}
          lastGenerateIncludedLetter={lastGenerateIncludedLetter}
        />

        <ApplicationAnswersPreview
          sectionNumber={answersSectionNumber}
          questions={applicationQuestions}
          answers={applicationAnswers}
          isGenerating={isGenerating}
          hasResume={Boolean(resume)}
          lastGenerateHadQuestions={lastGenerateHadQuestions}
        />
      </main>
      )}
      </div>
    </div>
  );
}

export default App;
