document.addEventListener("DOMContentLoaded", () => {
  // -----------------------------
  // Elements (match your template)
  // -----------------------------
  const form = document.getElementById("genForm");
  const fileInput = document.getElementById("id_document");
  const fileUiBtn = document.getElementById("fileUiBtn");
  const uploadOrb = document.getElementById("uploadOrb");
  const fileHint = document.getElementById("fileHint");

  const filePill = document.getElementById("filePill");
  const fileNameEl = document.getElementById("fileName");
  const fileSizeEl = document.getElementById("fileSize");
  const clearFileBtn = document.getElementById("clearFileBtn");

  const submitBtn = document.getElementById("submitBtn");
  const downloadBtn = document.getElementById("downloadBtn");

  const overlay = document.getElementById("overlay");
  const progressBar = document.getElementById("progressBar");
  const progressText = document.getElementById("progressText");

  const readyCard = document.getElementById("readyCard");
  const readyFilename = document.getElementById("readyFilename");

  const mInput = document.getElementById("mInput");
  const mOutput = document.getElementById("mOutput");
  const mTime = document.getElementById("mTime");
  const mReq = document.getElementById("mReq");
  const mTc = document.getElementById("mTc");
  const mNot = document.getElementById("mNot");

  // (si tu template todavía trae límite)
  const mLimit = document.getElementById("mLimit");
  const limitDetail = document.getElementById("limitDetail");
  const limitDetailList = document.getElementById("limitDetailList");

  const uploader = document.querySelector(".uploader");

  // ✅ NUEVO: Assigned To + métrica Area Path
  const assignedInput = document.getElementById("id_assigned_to");
  const mArea = document.getElementById("mArea");

  // Estado local (evita depender de fileInput.files en drag & drop)
  let selectedFile = null;

  let lastCsvB64 = null;
  let lastFilename = "TC.csv";

  // -----------------------------
  // i18n
  // -----------------------------
  const I18N = window.TCGEN_I18N || {
    // Errors
    ERR_NO_FILE: "Please upload a file to continue.",
    ERR_PROMPT_FILE: "Prompt file is invalid or missing.",
    ERR_BAD_EXT: "Unsupported file type. Allowed: .pdf, .docx.",
    ERR_TOO_LARGE: "The file exceeds the maximum allowed size.",
    ERR_NO_PROJECT_ID: "Project ID was not found in the document (expected 'ID proyecto').",
    ERR_NO_TOBE: "TO-BE section could not be extracted from the document.",
    ERR_NO_REQS: "No requirements were detected in the TO-BE section.",
    ERR_ENGINE: "An error occurred while generating test cases. Please check server logs.",
    ERR_ASSIGNED_TO: "Assigned To is required. Please use the exact display name from Azure DevOps.",

    // Success / status
    OK_GENERATED: "Test cases generated successfully.",
    UI_GENERATE_URL_MISSING: "Generate URL is not configured.",
    UI_DOWNLOAD_URL_MISSING: "Download URL is not configured.",
    UI_SELECT_FILE: "Please select a file before generating test cases.",
    UI_SELECT_ASSIGNED: "Please fill Assigned To with the exact Azure DevOps display name.",
    UI_STREAM_UNSUPPORTED: "Your browser does not support streaming responses.",
    UI_STREAM_ENDED: "The generation stream ended unexpectedly.",
    UI_DOWNLOAD_FAILED: "Download failed. Please generate test cases again.",
    UI_DOWNLOAD_STARTED: "Download started.",
    UI_UNEXPECTED_ERROR: "An unexpected error occurred. Please try again.",

    // Progress
    UI_STARTING: "Starting generation…",
    UI_PREPARING: "Preparing blocks…",
    UI_PROCESSING_REQ: "Processing requirement",
    UI_COMPLETED: "Completed. Ready to download.",
    UI_DONT_CLOSE: "Please do not close this window. This process may take a few minutes.",

    // Uploader UI
    UI_NO_FILE: "No file selected",
    UI_FILE_UPLOADED: "File uploaded",
    UI_SIZE: "Size",
    UI_UNSUPPORTED_FILE: "Unsupported file type. Allowed: .pdf, .docx",
    UI_ERROR_TITLE: "Error",
    UI_CLOSE: "Close",

    // Generic
    UI_REQUEST_FAILED: "Request failed. Please try again.",
  };

  function t(code, fallback) {
    if (code && I18N[code]) return I18N[code];
    return fallback || code || "";
  }

  // -----------------------------
  // Helpers
  // -----------------------------
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  function bytesToMB(bytes) {
    return (bytes / (1024 * 1024)).toFixed(2);
  }

  function show(el) { if (el) el.style.display = "block"; }
  function hide(el) { if (el) el.style.display = "none"; }

  const ALLOWED_EXTS = [".pdf", ".docx"];
  function isAllowedFile(file) {
    const name = (file?.name || "").toLowerCase();
    return ALLOWED_EXTS.some(ext => name.endsWith(ext));
  }

  function getAssignedToOrNull() {
    const v = (assignedInput?.value || "").trim();
    return v || null;
  }

  // -----------------------------
  // SweetAlert2 notifier (Toast + Modal)
  // -----------------------------
  const Toast = Swal.mixin({
    toast: true,
    position: "top-end",
    showConfirmButton: false,
    timer: 3200,
    timerProgressBar: true,
    showCloseButton: true,
    didOpen: (toast) => {
      toast.addEventListener("mouseenter", Swal.stopTimer);
      toast.addEventListener("mouseleave", Swal.resumeTimer);
    },
  });

  function showOk(message) {
    Toast.fire({ icon: "success", title: message });
  }

  function showError(message) {
    return Swal.fire({
      icon: "error",
      title: t("UI_ERROR_TITLE", "Error"),
      text: message,
      confirmButtonText: t("UI_CLOSE", "Close"),
      allowOutsideClick: true,
      allowEscapeKey: true,
    });
  }

  // Overlay uses CSS class ".show"
  function setOverlay(on) {
    if (!overlay) return;
    overlay.classList.toggle("show", on);
    overlay.setAttribute("aria-hidden", on ? "false" : "true");
  }

  function setProgress(pct, text) {
    const clamped = Math.max(0, Math.min(100, pct));
    if (progressBar) progressBar.style.width = `${clamped}%`;
    if (progressText && text) progressText.textContent = text;
  }

  function resetMetrics() {
    if (mInput) mInput.textContent = "0";
    if (mOutput) mOutput.textContent = "0";
    if (mTime) mTime.textContent = "0";
    if (mReq) mReq.textContent = "0";
    if (mTc) mTc.textContent = "0";
    if (mNot) mNot.textContent = "0";
    if (mArea) mArea.textContent = "-";

    // Si todavía existe la UI de límite, mantenerla en cero y oculta
    if (mLimit) mLimit.textContent = "0";
    if (limitDetail) limitDetail.hidden = true;
    if (limitDetailList) limitDetailList.innerHTML = "";
  }

  function resetUIForNewRun() {
    hide(readyCard);
    if (Swal.isVisible()) Swal.close();
    lastCsvB64 = null;
    lastFilename = "TC.csv";
    resetMetrics();
  }

  function setFileSelectedUI(file) {
    if (fileHint) fileHint.textContent = file ? file.name : t("UI_NO_FILE", "No file selected");

    if (!file) {
      if (filePill) hide(filePill);
      return;
    }

    if (fileNameEl) fileNameEl.textContent = `✅ ${t("UI_FILE_UPLOADED", "File uploaded")}: ${file.name}`;
    if (fileSizeEl) fileSizeEl.textContent = `${t("UI_SIZE", "Size")}: ${bytesToMB(file.size)} MB`;
    if (filePill) show(filePill);
  }

  function clearFileSelection() {
    selectedFile = null;
    if (fileInput) fileInput.value = "";
    setFileSelectedUI(null);
    resetUIForNewRun();
  }

  async function downloadCsvNoReload(downloadUrl) {
    const resp = await fetch(downloadUrl, {
      method: "GET",
      credentials: "same-origin",
    });

    if (!resp.ok) {
      throw new Error(t("UI_DOWNLOAD_FAILED", "Download failed. Please generate test cases again."));
    }

    const blob = await resp.blob();

    // Try to extract filename from Content-Disposition
    const cd = resp.headers.get("Content-Disposition") || "";
    let filename = "TC.csv";
    const match = cd.match(/filename="([^"]+)"/i);
    if (match && match[1]) filename = match[1];

    triggerDownload(blob, filename);
  }

  function base64ToUint8Array(b64) {
    const binary = atob(b64);
    const len = binary.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }

  function triggerDownload(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "TC.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  }

  function applyDoneUI(data) {
    if (readyFilename) readyFilename.textContent = data.filename || "TC.csv";

    if (mInput) mInput.textContent = String(data.usage?.input_tokens ?? 0);
    if (mOutput) mOutput.textContent = String(data.usage?.output_tokens ?? 0);
    if (mTime) mTime.textContent = String(data.elapsed ?? 0);

    const stats = data.stats || {};
    if (mReq) mReq.textContent = String(stats.requirements_total ?? 0);
    if (mTc) mTc.textContent = String(stats.test_cases_total ?? 0);
    if (mNot) mNot.textContent = String(stats.requirements_not_testable ?? 0);

    // ✅ Area Path = Project ID (según tu backend)
    if (mArea) mArea.textContent = String(stats.area_path ?? stats.project_id ?? "-");

    // Si existe UI de límite (hoy siempre será 0)
    if (mLimit) mLimit.textContent = String(stats.requirements_limit_reached_total ?? 0);

    // Detalle opcional del límite (normalmente vacío)
    const list = Array.isArray(stats.requirements_limit_reached_detail)
      ? stats.requirements_limit_reached_detail
      : [];
if (limitDetail && limitDetailList) {
  limitDetailList.innerHTML = "";

  if (list.length > 0) {
    for (const item of list) {
      const req = item.requirement ?? "?";
      const omitted = item.omitted_tcs;

      const li = document.createElement("li");
      li.textContent = Number.isFinite(omitted)
        ? `Req ${req}: (Limit reached) — omitidos ${omitted} TC`
        : `Req ${req}: (Limit reached)`;

      limitDetailList.appendChild(li);
    }
    limitDetail.hidden = false;
  } else {
    limitDetail.hidden = true;
  }
}

if (readyCard) show(readyCard);
}


  // -----------------------------
  // Streaming generator (NDJSON)
  // -----------------------------
  async function generateViaStream(streamUrl, formData, csrf) {
    const resp = await fetch(streamUrl, {
      method: "POST",
      body: formData,
      headers: { "X-CSRFToken": csrf },
      credentials: "same-origin",
    });

    // Validation errors may come as JSON (not a stream)
    const ct = (resp.headers.get("content-type") || "").toLowerCase();
    if (!resp.ok) {
      if (ct.includes("application/json")) {
        const j = await resp.json().catch(() => ({}));
        throw new Error(j.code ? t(j.code, j.message) : (j.message || t("UI_REQUEST_FAILED", "Request failed. Please try again.")));
      }
      const ttxt = await resp.text().catch(() => "");
      throw new Error(ttxt || t("UI_REQUEST_FAILED", "Request failed. Please try again."));
    }

    if (!resp.body || !resp.body.getReader) {
      throw new Error(t("UI_STREAM_UNSUPPORTED", "Your browser does not support streaming responses."));
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    let total = 0;
    const startedAt = performance.now();
    let done = 0;

    setProgress(2, t("UI_STARTING", "Starting generation…"));

    while (true) {
      const { value, done: doneReading } = await reader.read();
      if (doneReading) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) continue;

        let evt;
        try {
          evt = JSON.parse(line);
        } catch {
          continue;
        }

        if (evt.type === "meta") {
          total = evt.total_blocks || 0;
          setProgress(3, total
            ? `${t("UI_PREPARING", "Preparing blocks…")} (0/${total})`
            : t("UI_PREPARING", "Preparing blocks…")
          );
          continue;
        }

        if (evt.type === "progress") {
          done = evt.done || 0;
          total = evt.total || total;

          const pct = total ? Math.round((done / total) * 100) : 0;
          const elapsedSec = (performance.now() - startedAt) / 1000;
          const avg = done ? (elapsedSec / done) : 0;
          const etaSec = (avg && total) ? Math.max(0, Math.round(avg * (total - done))) : null;

          const req = evt.req ?? "?";
          const scenario = evt.scenario ? ` — ${evt.scenario}` : "";
          const etaTxt = (etaSec !== null) ? ` | ETA ~ ${etaSec}s` : "";

          setProgress(
            pct,
            `${t("UI_PROCESSING_REQ", "Processing requirement")} ${req}${scenario} (${done}/${total})${etaTxt}`
          );
          continue;
        }

        if (evt.type === "done") {
          setProgress(100, t("UI_COMPLETED", "Completed. Ready to download."));
          showOk(evt.code ? t(evt.code, evt.message) : (evt.message || t("OK_GENERATED", "Test cases generated successfully.")));
          applyDoneUI(evt);

          if (evt.csv_b64) {
            lastCsvB64 = evt.csv_b64;
            lastFilename = evt.filename || "TC.csv";
          } else {
            lastCsvB64 = null;
            lastFilename = evt.filename || "TC.csv";
          }
          return;
        }

        if (evt.type === "error") {
          throw new Error(t(evt.code, evt.message || t("ERR_ENGINE", "An error occurred while generating test cases.")));
        }
      }
    }

    throw new Error(t("UI_STREAM_ENDED", "The generation stream ended unexpectedly."));
  }

  // -----------------------------
  // Wire file picker
  // -----------------------------
  function selectFile(file) {
    if (file && !isAllowedFile(file)) {
      showError(t("UI_UNSUPPORTED_FILE", "Unsupported file type. Allowed: .pdf, .docx"))
        .then(() => clearFileSelection());
      return;
    }

    selectedFile = file || null;
    setFileSelectedUI(selectedFile);
    resetUIForNewRun();
  }

  if (fileUiBtn && fileInput) fileUiBtn.addEventListener("click", () => fileInput.click());
  if (uploadOrb && fileInput) uploadOrb.addEventListener("click", () => fileInput.click());

  if (fileInput) {
    fileInput.addEventListener("change", () => {
      const f = fileInput.files?.[0] || null;
      selectFile(f);
    });
  }

  if (clearFileBtn) {
    clearFileBtn.addEventListener("click", (e) => {
      e.preventDefault();
      clearFileSelection();
    });
  }

  // Drag & drop support (sin tocar fileInput.files)
  if (uploader) {
    uploader.addEventListener("dragover", (e) => {
      e.preventDefault();
      uploader.classList.add("is-dragover");
    });
    uploader.addEventListener("dragleave", () => uploader.classList.remove("is-dragover"));
    uploader.addEventListener("drop", (e) => {
      e.preventDefault();
      uploader.classList.remove("is-dragover");
      const files = e.dataTransfer?.files;
      if (files && files.length > 0) {
        selectFile(files[0]);
      }
    });
  }

  // Limpia el estado inválido cuando el usuario escribe
  if (assignedInput) {
    assignedInput.addEventListener("input", () => {
      assignedInput.classList.remove("is-invalid");
    });
  }

  // -----------------------------
  // Generate
  // -----------------------------
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const streamUrl = form.dataset.generateStreamUrl;
      if (!streamUrl) {
        showError(t("UI_GENERATE_URL_MISSING", "Generate URL is not configured."));
        return;
      }

      if (!selectedFile) {
        showError(t("UI_SELECT_FILE", "Please select a file before generating test cases."));
        return;
      }

      const assignedTo = getAssignedToOrNull();
      if (!assignedTo) {
        if (assignedInput) assignedInput.classList.add("is-invalid");
        await showError(t("UI_SELECT_ASSIGNED", "Please fill Assigned To with the exact Azure DevOps display name."));
        assignedInput?.focus();
        return;
      }

      resetUIForNewRun();
      setOverlay(true);
      setProgress(0, t("UI_DONT_CLOSE", "Please do not close this window. This process may take a few minutes."));
      if (submitBtn) submitBtn.disabled = true;

      try {
        const csrf = getCookie("csrftoken");

        // ✅ Importante: garantizamos que "document" sea el archivo seleccionado,
        // incluso si fue drag&drop y fileInput.files no se actualizó.
        const fd = new FormData(form);
        fd.set("document", selectedFile, selectedFile.name);

        // (assigned_to ya viene en el form, pero lo dejamos explícito por claridad)
        fd.set("assigned_to", assignedTo);

        await generateViaStream(streamUrl, fd, csrf);

      } catch (err) {
        showError(
          err?.message ||
          t("UI_UNEXPECTED_ERROR", "An unexpected error occurred. Please try again.")
        );
      } finally {
        setOverlay(false);
        if (submitBtn) submitBtn.disabled = false;
      }
    });
  }

  // -----------------------------
  // Download
  // -----------------------------
  if (downloadBtn && form) {
    downloadBtn.addEventListener("click", async () => {
      try {
        downloadBtn.disabled = true;

        // Preferred: download from memory (stream mode)
        if (lastCsvB64) {
          const bytes = base64ToUint8Array(lastCsvB64);
          const blob = new Blob([bytes], { type: "text/csv;charset=utf-8" });
          triggerDownload(blob, lastFilename);
          showOk(t("UI_DOWNLOAD_STARTED", "Download started."));
          return;
        }

        // Fallback: server download
        const downloadUrl = form.dataset.downloadUrl;
        if (!downloadUrl) {
          showError(t("UI_DOWNLOAD_URL_MISSING", "Download URL is not configured."));
          return;
        }

        await downloadCsvNoReload(downloadUrl);
        showOk(t("UI_DOWNLOAD_STARTED", "Download started."));

      } catch (err) {
        showError(err?.message || t("UI_DOWNLOAD_FAILED", "Download failed. Please generate test cases again."));
      } finally {
        downloadBtn.disabled = false;
      }
    });
  }

  // Init
  setFileSelectedUI(null);
  resetMetrics();
  hide(readyCard);
});
