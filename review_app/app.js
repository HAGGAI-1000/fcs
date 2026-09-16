"use strict";

const STORAGE_KEY = "fcs-expert-review-v2";
const LEGACY_STORAGE_KEY = "fcs-expert-review-v1";
const REVIEW_VERSION = 2;
const SNAPSHOT_DB_NAME = "fcs-expert-review";
const SNAPSHOT_DB_VERSION = 1;
const SNAPSHOT_STORE = "snapshots";
const SNAPSHOT_LIMIT = 20;
const OUTCOMES = new Set([
  "not_reviewed",
  "source_found",
  "source_not_found",
  "requires_non_fcs_source",
  "uncertain",
]);
const STATUSES = new Set(["pending", "approved"]);
const LEGACY_OUTCOMES = {
  "טרם נבדק": "not_reviewed",
  "נמצא מקור מתאים": "source_found",
  "לא נמצא מקור לאחר חיפוש": "source_not_found",
  "נדרש מקור מחוץ לאתר FCS": "requires_non_fcs_source",
  "לא ודאי": "uncertain",
};
const LEGACY_STATUSES = { "ממתין": "pending", "מאושר": "approved" };

const elements = {
  progressText: document.querySelector("#progress-text"),
  progressBar: document.querySelector("#progress-bar"),
  saveStatus: document.querySelector("#save-status"),
  questionSelect: document.querySelector("#question-select"),
  previousQuestion: document.querySelector("#previous-question"),
  nextQuestion: document.querySelector("#next-question"),
  questionNumber: document.querySelector("#question-number"),
  riskBadge: document.querySelector("#risk-badge"),
  questionHeading: document.querySelector("#question-heading"),
  reviewOutcome: document.querySelector("#review-outcome"),
  referenceAnswer: document.querySelector("#reference-answer"),
  reviewNotes: document.querySelector("#review-notes"),
  addSource: document.querySelector("#add-source"),
  sourcesList: document.querySelector("#sources-list"),
  questionErrors: document.querySelector("#question-errors"),
  questionSaveState: document.querySelector("#question-save-state"),
  saveQuestion: document.querySelector("#save-question"),
  openRecovery: document.querySelector("#open-recovery"),
  recoveryDialog: document.querySelector("#recovery-dialog"),
  closeRecovery: document.querySelector("#close-recovery"),
  snapshotList: document.querySelector("#snapshot-list"),
  exportReview: document.querySelector("#export-review"),
  importReview: document.querySelector("#import-review"),
  globalMessage: document.querySelector("#global-message"),
};

let questions = [];
let activeIndex = 0;
let state = { version: REVIEW_VERSION, reviews: {}, updatedAt: null };

function blankSource() {
  return { title: "", pages: "", date: "", url: "", notes: "" };
}

function blankReview() {
  return {
    outcome: "not_reviewed",
    status: "pending",
    answer: "",
    notes: "",
    sources: [blankSource()],
  };
}

function cleanSource(value) {
  return {
    title: String(value?.title ?? ""),
    pages: String(value?.pages ?? ""),
    date: String(value?.date ?? ""),
    url: String(value?.url ?? ""),
    notes: String(value?.notes ?? ""),
  };
}

function cleanReview(value) {
  const candidateOutcome = LEGACY_OUTCOMES[value?.outcome] ?? value?.outcome;
  const candidateStatus = LEGACY_STATUSES[value?.status] ?? value?.status;
  const outcome = OUTCOMES.has(candidateOutcome) ? candidateOutcome : "not_reviewed";
  const status = STATUSES.has(candidateStatus) ? candidateStatus : "pending";
  const sources = Array.isArray(value?.sources) && value.sources.length
    ? value.sources.map(cleanSource)
    : [blankSource()];
  return {
    outcome,
    status,
    answer: String(value?.answer ?? ""),
    notes: String(value?.notes ?? ""),
    sources,
  };
}

function sourceHasContent(source) {
  return Object.values(source).some((value) => String(value).trim());
}

function currentQuestion() {
  return questions[activeIndex];
}

function currentReview() {
  return state.reviews[currentQuestion().id];
}

function initializeState(stored) {
  const storedReviews = stored?.reviews && [1, REVIEW_VERSION].includes(stored?.version)
    ? stored.reviews
    : {};
  const reviews = {};
  for (const question of questions) {
    reviews[question.id] = cleanReview(storedReviews[question.id]);
  }
  state = {
    version: REVIEW_VERSION,
    reviews,
    updatedAt: stored?.updatedAt ?? null,
  };
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_error) {
    return null;
  }
}

function openSnapshotDatabase() {
  return new Promise((resolve, reject) => {
    if (!("indexedDB" in window)) {
      reject(new Error("הדפדפן אינו תומך בגרסאות שחזור מקומיות."));
      return;
    }
    const request = indexedDB.open(SNAPSHOT_DB_NAME, SNAPSHOT_DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(SNAPSHOT_STORE)) {
        const store = database.createObjectStore(SNAPSHOT_STORE, { keyPath: "id", autoIncrement: true });
        store.createIndex("createdAt", "createdAt");
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("פתיחת מאגר גרסאות השחזור נכשלה."));
  });
}

function cloneState() {
  return JSON.parse(JSON.stringify(state));
}

async function pruneSnapshots() {
  const database = await openSnapshotDatabase();
  try {
    await new Promise((resolve, reject) => {
      const transaction = database.transaction(SNAPSHOT_STORE, "readwrite");
      const store = transaction.objectStore(SNAPSHOT_STORE);
      const request = store.getAllKeys();
      request.onsuccess = () => {
        const excess = Math.max(0, request.result.length - SNAPSHOT_LIMIT);
        request.result.slice(0, excess).forEach((key) => store.delete(key));
      };
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("מחיקת גרסאות ישנות נכשלה."));
      transaction.onabort = () => reject(transaction.error ?? new Error("מחיקת גרסאות ישנות בוטלה."));
    });
  } finally {
    database.close();
  }
}

async function createSnapshot(reason, questionId = null) {
  const reviews = questions.map((question) => state.reviews[question.id]);
  const database = await openSnapshotDatabase();
  try {
    await new Promise((resolve, reject) => {
      const transaction = database.transaction(SNAPSHOT_STORE, "readwrite");
      transaction.objectStore(SNAPSHOT_STORE).add({
        createdAt: new Date().toISOString(),
        reason,
        questionId,
        activeQuestionId: currentQuestion()?.id ?? null,
        approvedCount: reviews.filter((review) => review.status === "approved").length,
        reviewedCount: reviews.filter((review) => review.outcome !== "not_reviewed").length,
        state: cloneState(),
      });
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("יצירת גרסת השחזור נכשלה."));
      transaction.onabort = () => reject(transaction.error ?? new Error("יצירת גרסת השחזור בוטלה."));
    });
  } finally {
    database.close();
  }
  await pruneSnapshots();
}

async function readSnapshots() {
  const database = await openSnapshotDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = database.transaction(SNAPSHOT_STORE, "readonly");
      const request = transaction.objectStore(SNAPSHOT_STORE).getAll();
      request.onsuccess = () => resolve(request.result.sort((left, right) => right.id - left.id));
      request.onerror = () => reject(request.error ?? new Error("קריאת גרסאות השחזור נכשלה."));
    });
  } finally {
    database.close();
  }
}

async function readSnapshot(id) {
  const database = await openSnapshotDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = database.transaction(SNAPSHOT_STORE, "readonly");
      const request = transaction.objectStore(SNAPSHOT_STORE).get(id);
      request.onsuccess = () => resolve(request.result ?? null);
      request.onerror = () => reject(request.error ?? new Error("קריאת גרסת השחזור נכשלה."));
    });
  } finally {
    database.close();
  }
}

function saveState() {
  state.updatedAt = new Date().toISOString();
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    elements.saveStatus.textContent = `נשמר מקומית ${new Date().toLocaleTimeString("he-IL", {
      hour: "2-digit",
      minute: "2-digit",
    })}`;
  } catch (_error) {
    elements.saveStatus.textContent = "השמירה האוטומטית בדפדפן נכשלה";
  }
  updateProgress();
}

function riskLabel(value) {
  if (value === "high") return "סיכון גבוה";
  if (value === "medium") return "סיכון בינוני";
  return "סיכון נמוך";
}

function updateProgress() {
  const reviews = questions.map((question) => state.reviews[question.id]);
  const reviewed = reviews.filter((review) => review.outcome !== "not_reviewed").length;
  const approved = reviews.filter((review) => review.status === "approved").length;
  const percent = questions.length ? (reviewed / questions.length) * 100 : 0;
  elements.progressText.textContent = `${reviewed} מתוך ${questions.length} שאלות נבדקו · ${approved} אושרו`;
  elements.progressBar.style.width = `${percent}%`;
  elements.questionSelect.querySelectorAll("option").forEach((option, index) => {
    const review = state.reviews[questions[index].id];
    const marker = review.status === "approved" ? "✓" : review.outcome !== "not_reviewed" ? "•" : "";
    option.textContent = `${marker} שאלה ${index + 1}`.trim();
  });
}

function updateQuestionSaveState() {
  const review = questions.length ? currentReview() : null;
  const isApproved = review?.status === "approved";
  elements.questionSaveState.textContent = isApproved
    ? "השאלה נבדקה, נשמרה ואושרה."
    : "הטיוטה נשמרת אוטומטית. לחיצה על הכפתור תבדוק ותאשר את השאלה.";
  elements.saveQuestion.textContent = isApproved ? "שמירה מחדש" : "שמירת השאלה";
}

function createLabeledInput(labelText, type, value, field, sourceIndex, className = "") {
  const label = document.createElement("label");
  if (className) label.className = className;
  const labelSpan = document.createElement("span");
  labelSpan.textContent = labelText;
  const input = type === "textarea" ? document.createElement("textarea") : document.createElement("input");
  if (type !== "textarea") input.type = type;
  if (type === "textarea") input.rows = 3;
  input.value = value;
  input.dataset.sourceIndex = String(sourceIndex);
  input.dataset.sourceField = field;
  label.append(labelSpan, input);
  return label;
}

function renderSources(review) {
  elements.sourcesList.replaceChildren();
  review.sources.forEach((source, index) => {
    const card = document.createElement("article");
    card.className = "source-card";

    const heading = document.createElement("h4");
    heading.textContent = `מקור ${index + 1}`;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "button danger remove-source";
    remove.textContent = "הסר מקור";
    remove.dataset.removeSource = String(index);
    remove.setAttribute("aria-label", `הסר מקור ${index + 1}`);

    const grid = document.createElement("div");
    grid.className = "source-grid";
    grid.append(
      createLabeledInput("שם המסמך בדיוק כפי שהוא מופיע ב-FCS", "text", source.title, "title", index, "wide"),
      createLabeledInput("עמודים רלוונטיים", "text", source.pages, "pages", index),
      createLabeledInput("תאריך פרסום או עדכון", "date", source.date, "date", index),
      createLabeledInput("כתובת FCS", "url", source.url, "url", index, "wide"),
      createLabeledInput("הערות למקור", "textarea", source.notes, "notes", index),
    );
    card.append(heading, remove, grid);
    elements.sourcesList.append(card);
  });
}

function render() {
  const question = currentQuestion();
  const review = currentReview();
  elements.questionSelect.value = String(activeIndex);
  elements.previousQuestion.disabled = activeIndex === 0;
  elements.nextQuestion.disabled = activeIndex === questions.length - 1;
  elements.questionNumber.textContent = `שאלה ${activeIndex + 1} מתוך ${questions.length}`;
  elements.riskBadge.textContent = riskLabel(question.risk_level);
  elements.questionHeading.textContent = question.question;
  elements.reviewOutcome.value = review.outcome;
  elements.referenceAnswer.value = review.answer;
  elements.reviewNotes.value = review.notes;
  renderSources(review);
  showQuestionErrors([]);
  updateProgress();
  updateQuestionSaveState();
}

function isValidFcsUrl(value) {
  if (!value.trim()) return true;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" && parsed.hostname.toLowerCase() === "fcs.health.gov.il";
  } catch (_error) {
    return false;
  }
}

function validateQuestion(question, review) {
  const errors = [];
  const completedSources = review.sources.filter(sourceHasContent);
  const seenSources = new Set();

  completedSources.forEach((source, index) => {
    const sourceNumber = index + 1;
    if (!source.title.trim()) errors.push(`מקור ${sourceNumber}: חסר שם מסמך.`);
    if (!source.pages.trim()) errors.push(`מקור ${sourceNumber}: חסרים עמודים רלוונטיים.`);
    if (!isValidFcsUrl(source.url)) errors.push(`מקור ${sourceNumber}: כתובת המקור חייבת להיות HTTPS באתר fcs.health.gov.il.`);
    const duplicateKey = `${source.title.trim().toLocaleLowerCase("he")}|${source.date}`;
    if (source.title.trim() && seenSources.has(duplicateKey)) {
      errors.push(`מקור ${sourceNumber}: נראה שמדובר במקור כפול.`);
    }
    seenSources.add(duplicateKey);
  });

  if (review.status === "approved") {
    if (!review.answer.trim()) errors.push("שאלה מאושרת חייבת לכלול תשובת ייחוס בעברית.");
    if (review.outcome === "source_found" && completedSources.length === 0) {
      errors.push("שאלה עם מקור מתאים חייבת לכלול לפחות מקור אחד.");
    }
    if (review.outcome === "requires_non_fcs_source" && completedSources.length > 0) {
      errors.push("שאלה שמחייבת מקור מחוץ ל-FCS אינה יכולה לכלול מקור FCS שאושר כתשובה.");
    }
    if (["not_reviewed", "source_not_found", "uncertain"].includes(review.outcome)) {
      errors.push("לא ניתן לאשר שאלה עם תוצאת הבדיקה שנבחרה.");
    }
  }

  const questionNumber = Number(String(question.id).replace(/\D/g, "")) || question.id;
  return errors.map((message) => `שאלה ${questionNumber}: ${message}`);
}

function showQuestionErrors(errors) {
  elements.questionErrors.hidden = errors.length === 0;
  elements.questionErrors.textContent = errors.join("\n");
}

function validateAllReviews() {
  return questions.flatMap((question) => validateQuestion(question, state.reviews[question.id]));
}

function showGlobal(message, type = "success") {
  elements.globalMessage.className = `global-message ${type}`;
  elements.globalMessage.textContent = message;
}

function changeQuestion(index) {
  activeIndex = Math.max(0, Math.min(questions.length - 1, index));
  render();
  document.querySelector("#review-form").scrollIntoView({ behavior: "smooth", block: "start" });
}

function updateCurrentReview(field, value) {
  const review = currentReview();
  review[field] = value;
  review.status = "pending";
  saveState();
  updateQuestionSaveState();
}

async function saveCurrentQuestion() {
  if (elements.saveQuestion.disabled) return;
  elements.saveQuestion.disabled = true;
  const question = currentQuestion();
  const review = currentReview();
  review.status = "approved";
  const errors = validateQuestion(question, review);
  if (errors.length) {
    review.status = "pending";
    saveState();
    updateQuestionSaveState();
    showQuestionErrors(errors);
    elements.questionErrors.scrollIntoView({ behavior: "smooth", block: "center" });
    elements.saveQuestion.disabled = false;
    return;
  }

  showQuestionErrors([]);
  saveState();
  updateQuestionSaveState();
  try {
    await createSnapshot("question_saved", question.id);
    showGlobal(`שאלה ${activeIndex + 1} נבדקה ונשמרה. נוצרה גם גרסת שחזור.`);
  } catch (error) {
    showGlobal(`השאלה נשמרה ואושרה, אך יצירת גרסת השחזור נכשלה: ${error.message}`, "error");
  } finally {
    elements.saveQuestion.disabled = false;
  }
}

function snapshotReasonLabel(snapshot) {
  if (snapshot.reason === "question_saved" && snapshot.questionId) {
    const questionNumber = Number(String(snapshot.questionId).replace(/\D/g, ""));
    return `לאחר שמירת שאלה ${questionNumber || snapshot.questionId}`;
  }
  if (snapshot.reason === "import") return "לאחר ייבוא קובץ תוצאות";
  if (snapshot.reason === "before_restore") return "לפני שחזור גרסה אחרת";
  return "גרסה שמורה";
}

function renderSnapshotList(snapshots) {
  elements.snapshotList.replaceChildren();
  if (!snapshots.length) {
    const empty = document.createElement("p");
    empty.className = "empty-snapshots";
    empty.textContent = "עדיין אין גרסאות שחזור. גרסה תיווצר לאחר שמירת שאלה.";
    elements.snapshotList.append(empty);
    return;
  }

  snapshots.forEach((snapshot) => {
    const item = document.createElement("article");
    item.className = "snapshot-item";
    const copy = document.createElement("div");
    const heading = document.createElement("strong");
    heading.textContent = new Date(snapshot.createdAt).toLocaleString("he-IL", {
      dateStyle: "short",
      timeStyle: "short",
    });
    const details = document.createElement("span");
    details.textContent = `${snapshotReasonLabel(snapshot)} · ${snapshot.reviewedCount} נבדקו · ${snapshot.approvedCount} נשמרו`;
    copy.append(heading, details);

    const restore = document.createElement("button");
    restore.type = "button";
    restore.className = "button secondary";
    restore.textContent = "שחזור גרסה זו";
    restore.dataset.restoreSnapshot = String(snapshot.id);
    item.append(copy, restore);
    elements.snapshotList.append(item);
  });
}

async function openRecoveryDialog() {
  try {
    renderSnapshotList(await readSnapshots());
    elements.recoveryDialog.showModal();
  } catch (error) {
    showGlobal(`לא ניתן לפתוח את גרסאות השחזור: ${error.message}`, "error");
  }
}

async function restoreSnapshot(id) {
  try {
    const snapshot = await readSnapshot(id);
    if (!snapshot) throw new Error("גרסת השחזור שנבחרה אינה קיימת.");
    await createSnapshot("before_restore");
    initializeState(snapshot.state);
    const restoredIndex = questions.findIndex((question) => question.id === snapshot.activeQuestionId);
    activeIndex = restoredIndex >= 0 ? restoredIndex : 0;
    saveState();
    render();
    elements.recoveryDialog.close();
    showGlobal("הגרסה שוחזרה. המצב שהיה לפני השחזור נשמר כגרסת שחזור נוספת.");
  } catch (error) {
    showGlobal(`שחזור הגרסה נכשל: ${error.message}`, "error");
  }
}

function download(name, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function canExport() {
  const errors = validateAllReviews();
  if (errors.length) {
    showGlobal(`יש לתקן ${errors.length} בעיות לפני ייצוא:\n${errors.slice(0, 8).join("\n")}`, "error");
    const firstId = errors[0].match(/שאלה (\d+)/)?.[1];
    if (firstId) changeQuestion(Number(firstId) - 1);
    return false;
  }
  return true;
}

function canonicalReview() {
  return {
    schema_version: REVIEW_VERSION,
    exported_at: new Date().toISOString(),
    question_count: questions.length,
    reviews: questions.map((question) => {
      const review = state.reviews[question.id];
      return {
        question_id: question.id,
        question_text_he: question.question,
        outcome: review.outcome,
        review_status: review.status,
        reference_answer_he: review.answer,
        review_notes: review.notes,
        sources: review.sources.filter(sourceHasContent).map((source) => ({
          document_title: source.title,
          relevant_pages: source.pages,
          publication_or_update_date: source.date,
          fcs_url: source.url,
          source_notes: source.notes,
        })),
      };
    }),
  };
}

function exportReview() {
  if (!canExport()) return;
  download(
    "eval_relevance_expert.json",
    `${JSON.stringify(canonicalReview(), null, 2)}\n`,
    "application/json;charset=utf-8",
  );
  showGlobal("קובץ התוצאות יוצא בהצלחה.");
}

function stateFromCanonical(parsed) {
  if (parsed?.schema_version !== REVIEW_VERSION || !Array.isArray(parsed?.reviews)) {
    throw new Error("מבנה הקובץ אינו מתאים לגרסה הנוכחית.");
  }
  if (parsed.reviews.length !== questions.length) {
    throw new Error("מספר השאלות בקובץ אינו מתאים.");
  }
  const reviews = {};
  parsed.reviews.forEach((item, index) => {
    const question = questions[index];
    if (item?.question_id !== question.id || item?.question_text_he !== question.question) {
      throw new Error(`השאלה ${index + 1} אינה תואמת לקובץ השאלות הנוכחי.`);
    }
    reviews[question.id] = cleanReview({
      outcome: item.outcome,
      status: item.review_status,
      answer: item.reference_answer_he,
      notes: item.review_notes,
      sources: Array.isArray(item.sources)
        ? item.sources.map((source) => ({
            title: source.document_title,
            pages: source.relevant_pages,
            date: source.publication_or_update_date,
            url: source.fcs_url,
            notes: source.source_notes,
          }))
        : [],
    });
  });
  return { version: REVIEW_VERSION, reviews, updatedAt: parsed.exported_at ?? null };
}

async function importReview(file) {
  try {
    const parsed = JSON.parse(await file.text());
    const imported = Array.isArray(parsed?.reviews) ? stateFromCanonical(parsed) : parsed;
    initializeState(imported);
    saveState();
    activeIndex = 0;
    render();
    try {
      await createSnapshot("import");
      showGlobal("קובץ התוצאות יובא בהצלחה ונוצרה גרסת שחזור.");
    } catch (snapshotError) {
      showGlobal(`קובץ התוצאות יובא, אך יצירת גרסת השחזור נכשלה: ${snapshotError.message}`, "error");
    }
  } catch (error) {
    showGlobal(`ייבוא קובץ התוצאות נכשל: ${error.message}`, "error");
  } finally {
    elements.importReview.value = "";
  }
}

function bindEvents() {
  elements.questionSelect.addEventListener("change", () => changeQuestion(Number(elements.questionSelect.value)));
  elements.previousQuestion.addEventListener("click", () => changeQuestion(activeIndex - 1));
  elements.nextQuestion.addEventListener("click", () => changeQuestion(activeIndex + 1));
  elements.reviewOutcome.addEventListener("change", () => updateCurrentReview("outcome", elements.reviewOutcome.value));
  elements.referenceAnswer.addEventListener("input", () => updateCurrentReview("answer", elements.referenceAnswer.value));
  elements.reviewNotes.addEventListener("input", () => updateCurrentReview("notes", elements.reviewNotes.value));
  elements.addSource.addEventListener("click", () => {
    const review = currentReview();
    review.sources.push(blankSource());
    review.status = "pending";
    saveState();
    updateQuestionSaveState();
    renderSources(currentReview());
    elements.sourcesList.lastElementChild?.querySelector("input")?.focus();
  });
  elements.sourcesList.addEventListener("input", (event) => {
    const input = event.target.closest("[data-source-field]");
    if (!input) return;
    const index = Number(input.dataset.sourceIndex);
    const review = currentReview();
    review.sources[index][input.dataset.sourceField] = input.value;
    review.status = "pending";
    saveState();
    updateQuestionSaveState();
  });
  elements.sourcesList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-source]");
    if (!button) return;
    const index = Number(button.dataset.removeSource);
    const sources = currentReview().sources;
    if (sources.length === 1) sources[0] = blankSource();
    else sources.splice(index, 1);
    currentReview().status = "pending";
    saveState();
    updateQuestionSaveState();
    renderSources(currentReview());
  });
  elements.saveQuestion.addEventListener("click", saveCurrentQuestion);
  elements.openRecovery.addEventListener("click", openRecoveryDialog);
  elements.closeRecovery.addEventListener("click", () => elements.recoveryDialog.close());
  elements.snapshotList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-restore-snapshot]");
    if (!button || button.disabled) return;
    button.disabled = true;
    await restoreSnapshot(Number(button.dataset.restoreSnapshot));
    button.disabled = false;
  });
  elements.exportReview.addEventListener("click", exportReview);
  elements.importReview.addEventListener("change", () => {
    const file = elements.importReview.files?.[0];
    if (file) importReview(file);
  });
}

async function initialize() {
  try {
    const response = await fetch("questions.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`טעינת השאלות נכשלה (${response.status})`);
    questions = await response.json();
    if (!Array.isArray(questions) || questions.length !== 50) {
      throw new Error("קובץ השאלות אינו מכיל 50 שאלות.");
    }
    initializeState(loadState());
    questions.forEach((_question, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      elements.questionSelect.append(option);
    });
    bindEvents();
    render();
  } catch (error) {
    showGlobal(`היישום לא נטען: ${error.message}`, "error");
    elements.progressText.textContent = "טעינת השאלות נכשלה";
  }
}

initialize();
