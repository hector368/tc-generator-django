document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("pepForm");
  const papInput = document.getElementById("id_pap_document");
  const pddInput = document.getElementById("id_pdd_document");
  const selectedRequirementsInput = document.getElementById("selectedRequirements");

  const previewBtn = document.getElementById("previewBtn");
  const generatePepBtn = document.getElementById("generatePepBtn");
  const selectReqBtn = document.getElementById("pepSelectReqBtn");
  const papInfoBtn = document.getElementById("papInfoBtn");
  const pddInfoBtn = document.getElementById("pddInfoBtn");
  const viewJsonBtn = document.getElementById("viewJsonBtn");

  const previewCard = document.getElementById("pepPreviewCard");
  const pepFilename = document.getElementById("pepFilename");
  const pepProjectId = document.getElementById("pepProjectId");
  const pepClient = document.getElementById("pepClient");
  const pepTechnology = document.getElementById("pepTechnology");
  const pepDetectionType = document.getElementById("pepDetectionType");
  const pepFilenameMetric = document.getElementById("pepFilenameMetric");

  const pepTechnologyJustification = document.getElementById("pepTechnologyJustification");
  const pepTechnologyJustificationText = document.getElementById("pepTechnologyJustificationText");
  const pepHardware = document.getElementById("pepHardware");
  const pepCost = document.getElementById("pepCost");
  const pepReqTotal = document.getElementById("pepReqTotal");
  const pepReqSelected = document.getElementById("pepReqSelected");

  const warningsBox = document.getElementById("pepWarnings");
  const warningsList = document.getElementById("pepWarningsList");

  const overlay = document.getElementById("overlay");
  const overlayTitle = document.getElementById("overlayTitle");
  const progressText = document.getElementById("progressText");
  const progressBar = document.getElementById("progressBar");

  let lastPreview = null;
  let selectedReqNums = null;

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

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  function showOk(message) {
    Toast.fire({ icon: "success", title: message });
  }

  function showError(message) {
    return Swal.fire({
      icon: "error",
      title: "Error",
      text: message,
      confirmButtonText: "Close",
      allowOutsideClick: true,
      allowEscapeKey: true,
    });
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function setOverlay(on, title, text, percent) {
    if (!overlay) return;

    overlay.classList.toggle("show", on);
    overlay.setAttribute("aria-hidden", on ? "false" : "true");

    if (overlayTitle && title) overlayTitle.textContent = title;
    if (progressText && text) progressText.textContent = text;
    if (progressBar) progressBar.style.width = `${percent || 0}%`;
  }

  function resetPreview() {
    lastPreview = null;
    selectedReqNums = null;

    if (selectedRequirementsInput) selectedRequirementsInput.value = "";
    if (previewCard) previewCard.style.display = "none";
  }

  function getFile(input) {
    return input?.files?.[0] || null;
  }

  function validateFiles() {
    const papFile = getFile(papInput);
    const pddFile = getFile(pddInput);

    if (!papFile) {
      throw new Error("Debes subir el documento PAP.");
    }

    if (!pddFile) {
      throw new Error("Debes subir el documento PDD/FDD.");
    }

    return { papFile, pddFile };
  }

  function buildFormData() {
    const { papFile, pddFile } = validateFiles();

    const fd = new FormData();
    fd.set("pap_document", papFile, papFile.name);
    fd.set("pdd_document", pddFile, pddFile.name);

    const selected = selectedRequirementsInput?.value?.trim() || "";
    if (selected) {
      fd.set("selected_requirements", selected);
    }

    return fd;
  }

  function renderPreview(data) {
  lastPreview = data;

  const pap = data?.pap || {};
  const tobe = data?.tobe || {};
  const requirements = Array.isArray(tobe.requirements)
    ? tobe.requirements
    : [];

  const technology = pap.tecnologia || {};

  if (pepFilename) {
    pepFilename.textContent = data.output_filename || "PEP.docx";
  }

  if (pepFilenameMetric) {
    pepFilenameMetric.textContent = data.output_filename || "PEP.docx";
  }

  if (pepProjectId) {
    pepProjectId.textContent = data.project_id || "-";
  }

  if (pepClient) {
    pepClient.textContent = pap.nombre_cliente || "-";
  }

  if (pepTechnology) {
    pepTechnology.textContent = technology.valor || "-";
  }

  if (pepDetectionType) {
    pepDetectionType.textContent = formatDetectionType(
      technology.tipo_deteccion
    );
  }

  if (pepCost) {
    pepCost.textContent = data.cost?.total_usd_formatted || "$0.00";
  }

  renderTechnologyJustification(technology.justificacion);

  if (pepReqTotal) {
    pepReqTotal.textContent = String(
      tobe.total_blocks ?? requirements.length
    );
  }

  selectedReqNums = null;
  updateSelectedRequirementsInput();
  updateSelectedCount();

  renderWarnings(data.warnings || []);

  if (previewCard) {
    previewCard.style.display = "block";
  }
}

function formatDetectionType(value) {
  const normalized = String(value || "").trim().toLowerCase();

  if (normalized === "explicita") return "Explicit";
  if (normalized === "inferida") return "Inferred";
  if (normalized === "no_encontrada") return "Not found";

  return "-";
}


function renderTechnologyJustification(justification) {
  if (!pepTechnologyJustification || !pepTechnologyJustificationText) return;

  const text = String(justification || "").trim();

  if (!text) {
    pepTechnologyJustification.hidden = true;
    pepTechnologyJustificationText.textContent = "-";
    return;
  }

  pepTechnologyJustificationText.textContent = text;
  pepTechnologyJustification.hidden = false;
}


function buildExecutionJson() {
  const requirements = getRequirements();

  const selectedRequirements = selectedReqNums === null
    ? requirements.map((req) => Number(req.number))
    : selectedReqNums;

  return {
    ...lastPreview,
    execution_selection: {
      selected_requirements: selectedRequirements,
      selected_count: selectedRequirements.length,
      all_requirements_selected: selectedReqNums === null,
    },
  };
}


function openJsonModal() {
  if (!lastPreview) {
    showError("Primero genera la previsualización.");
    return;
  }

  const executionJson = buildExecutionJson();
  const prettyJson = JSON.stringify(executionJson, null, 2);

  Swal.fire({
    title: "Execution JSON",
    html: `
      <pre style="
        text-align:left;
        max-height:60vh;
        overflow:auto;
        white-space:pre-wrap;
        word-break:break-word;
        background:rgba(16,24,40,0.06);
        border:1px solid rgba(98,0,208,0.14);
        border-radius:14px;
        padding:14px;
        font-size:12px;
        line-height:1.45;
      ">${escapeHtml(prettyJson)}</pre>
    `,
    width: "min(1100px, 94vw)",
    showCancelButton: true,
    confirmButtonText: "Copy JSON",
    cancelButtonText: "Close",
    allowOutsideClick: true,
    allowEscapeKey: true,
  }).then(async (result) => {
    if (!result.isConfirmed) return;

    try {
      await navigator.clipboard.writeText(prettyJson);
      showOk("JSON copied to clipboard.");
    } catch {
      showError("No se pudo copiar el JSON.");
    }
  });
}

  function renderWarnings(warnings) {
    if (!warningsBox || !warningsList) return;

    warningsList.innerHTML = "";

    if (!Array.isArray(warnings) || warnings.length === 0) {
      warningsBox.hidden = true;
      return;
    }

    for (const warning of warnings) {
      const li = document.createElement("li");
      li.textContent = warning;
      warningsList.appendChild(li);
    }

    warningsBox.hidden = false;
  }

  function getRequirements() {
    const reqs = lastPreview?.tobe?.requirements;
    return Array.isArray(reqs) ? reqs : [];
  }

  function updateSelectedCount() {
    if (!pepReqSelected) return;

    const requirements = getRequirements();

    const selectedCount = selectedReqNums === null
      ? requirements.length
      : selectedReqNums.length;

    pepReqSelected.textContent = String(selectedCount);
  }

  function updateSelectedRequirementsInput() {
    if (!selectedRequirementsInput) return;

    if (selectedReqNums === null) {
      selectedRequirementsInput.value = "";
      return;
    }

    selectedRequirementsInput.value = selectedReqNums.join(",");
  }

  function openRequirementsModal() {
    const requirements = getRequirements();

    if (!requirements.length) {
      showError("No hay requerimientos detectados para seleccionar.");
      return;
    }

    const preselected = selectedReqNums === null
      ? new Set(requirements.map((req) => Number(req.number)))
      : new Set(selectedReqNums.map(Number));

    const html = `
      <div class="req-modal">
        <div class="req-modal__header">
          <div class="req-modal__title">Select TO-BE Requirements</div>
          <div class="req-modal__badges">
            <span class="badge-mini">📌 Requirements: ${requirements.length}</span>
            <span class="badge-mini">✅ Selected: <span id="modalSelCount">0</span></span>
          </div>

          <div class="req-modal__toolbar">
            <div class="req-toolbar__actions">
              <button type="button" class="req-chip" id="selAllBtn">
                <span class="req-chip__icon">✅</span>
                Select all
              </button>

              <button type="button" class="req-chip req-chip--ghost" id="selNoneBtn">
                <span class="req-chip__icon">🧹</span>
                Clear
              </button>
            </div>

            <input type="text" class="input" id="selSearch" placeholder="Search..." />
          </div>
        </div>

        <div class="req-modal__list">
          <ul class="req-list" id="reqSelectList">
            ${
              requirements.map((req) => {
                const number = Number(req.number);
                const checked = preselected.has(number) ? "checked" : "";

                return `
                  <li class="req-item">
                    <label class="req-check">
                      <input type="checkbox"
                             class="req-checkbox"
                             data-num="${escapeHtml(number)}"
                             ${checked} />
                      <span class="req-num">${escapeHtml(number)}.</span>
                      <span class="req-title">${escapeHtml(req.title || "")}</span>
                    </label>
                  </li>
                `;
              }).join("")
            }
          </ul>
        </div>
      </div>
    `;

    Swal.fire({
      title: "",
      html,
      width: "min(980px, 92vw)",
      showCancelButton: true,
      confirmButtonText: "Apply selection",
      cancelButtonText: "Cancel",
      allowOutsideClick: true,
      allowEscapeKey: true,
      didOpen: () => {
        const root = Swal.getHtmlContainer();
        const checkboxes = Array.from(root.querySelectorAll(".req-checkbox"));
        const selCount = root.querySelector("#modalSelCount");
        const allBtn = root.querySelector("#selAllBtn");
        const noneBtn = root.querySelector("#selNoneBtn");
        const search = root.querySelector("#selSearch");
        const list = root.querySelector("#reqSelectList");

        const updateCount = () => {
          const count = checkboxes.filter((cb) => cb.checked).length;
          if (selCount) selCount.textContent = String(count);
        };

        updateCount();

        checkboxes.forEach((cb) => {
          cb.addEventListener("change", updateCount);
        });

        if (allBtn) {
          allBtn.addEventListener("click", () => {
            checkboxes.forEach((cb) => cb.checked = true);
            updateCount();
          });
        }

        if (noneBtn) {
          noneBtn.addEventListener("click", () => {
            checkboxes.forEach((cb) => cb.checked = false);
            updateCount();
          });
        }

        if (search && list) {
          search.addEventListener("input", () => {
            const query = search.value.trim().toLowerCase();
            const items = Array.from(list.querySelectorAll(".req-item"));

            for (const item of items) {
              item.style.display = item.textContent
                .toLowerCase()
                .includes(query) ? "" : "none";
            }
          });
        }
      },
      preConfirm: () => {
        const root = Swal.getHtmlContainer();
        const checkboxes = Array.from(root.querySelectorAll(".req-checkbox"));

        const selected = checkboxes
          .filter((cb) => cb.checked)
          .map((cb) => Number(cb.dataset.num))
          .filter((num) => Number.isFinite(num));

        if (selected.length === 0) {
          Swal.showValidationMessage("Selecciona al menos un requerimiento.");
          return false;
        }

        return selected;
      },
    }).then((result) => {
      if (!result.isConfirmed) return;

      const selected = Array.isArray(result.value) ? result.value : [];

      if (selected.length === requirements.length) {
        selectedReqNums = null;
      } else {
        selectedReqNums = selected;
      }

      updateSelectedRequirementsInput();
      updateSelectedCount();
    });
  }
  function openPapInfoModal() {
  Swal.fire({
    icon: "info",
    title: "PAP document requirements",
    html: `
      <div style="text-align:left; line-height:1.55;">
        <p>
          The PAP is used to extract the administrative and technical
          information needed to fill the PEP.
        </p>

        <p><strong>Recommended content:</strong></p>
        <ul>
          <li>Project name and project ID.</li>
          <li>Client name.</li>
          <li>Project technology or enough evidence to infer it.</li>
          <li>Project roles and responsible people.</li>
          <li>Software requirements.</li>
          <li>Hardware requirements.</li>
        </ul>

        <p><strong>Important:</strong></p>
        <ul>
          <li>If a field is missing, it may be filled as N/A or reported as a warning.</li>
          <li>The automation does not invent missing information.</li>
          <li>Technology may be explicit or inferred from document evidence.</li>
        </ul>
      </div>
    `,
    confirmButtonText: "Understood",
    width: "min(760px, 92vw)",
  });
}


function openPddInfoModal() {
  Swal.fire({
    icon: "info",
    title: "PDD/FDD document requirements",
    html: `
      <div style="text-align:left; line-height:1.55;">
        <p>
          The PDD/FDD is used to detect the TO-BE requirement titles that
          will be inserted into section 5.1 of the PEP.
        </p>

        <p><strong>Recommended content:</strong></p>
        <ul>
          <li>A clear TO-BE section or equivalent requirement section.</li>
          <li>Numbered requirements or identifiable functional modules.</li>
          <li>Requirement titles written clearly.</li>
          <li>Project ID, when available, to compare against the PAP.</li>
        </ul>

        <p><strong>Important:</strong></p>
        <ul>
          <li>The detected requirements will be shown before generating the PEP.</li>
          <li>You can select or unselect requirements before downloading the document.</li>
          <li>If the project ID differs from the PAP, the system will show a warning.</li>
        </ul>
      </div>
    `,
    confirmButtonText: "Understood",
    width: "min(760px, 92vw)",
  });
}
  async function requestPreview() {
    if (!form) return;

    const previewUrl = form.dataset.previewUrl;
    if (!previewUrl) {
      showError("Preview URL is not configured.");
      return;
    }

    try {
      const fd = buildFormData();
      const csrf = getCookie("csrftoken");

      setOverlay(
        true,
        "Analyzing documents",
        "Extracting PAP information and TO-BE requirements...",
        35
      );

      if (previewBtn) previewBtn.disabled = true;

      const resp = await fetch(previewUrl, {
        method: "POST",
        body: fd,
        headers: { "X-CSRFToken": csrf },
        credentials: "same-origin",
      });

      const data = await resp.json().catch(() => null);

      if (!resp.ok) {
        throw new Error(data?.message || "No se pudo generar la previsualización.");
      }

      renderPreview(data);
      showOk("Preview generated successfully.");
    } catch (err) {
      showError(err?.message || "No se pudo generar la previsualización.");
    } finally {
      setOverlay(false);
      if (previewBtn) previewBtn.disabled = false;
    }
  }

  async function generatePep() {
    if (!form) return;

    const generateUrl = form.dataset.generateUrl;
    if (!generateUrl) {
      showError("Generate URL is not configured.");
      return;
    }

    if (!lastPreview) {
      showError("Primero genera la previsualización.");
      return;
    }

    try {
      const fd = buildFormData();
      const csrf = getCookie("csrftoken");

      setOverlay(
        true,
        "Generating PEP",
        "Building the DOCX document...",
        70
      );

      if (generatePepBtn) generatePepBtn.disabled = true;

      const resp = await fetch(generateUrl, {
        method: "POST",
        body: fd,
        headers: { "X-CSRFToken": csrf },
        credentials: "same-origin",
      });

      if (!resp.ok) {
        const contentType = (resp.headers.get("content-type") || "").toLowerCase();
        if (contentType.includes("application/json")) {
          const data = await resp.json().catch(() => null);
          throw new Error(data?.message || "No se pudo generar el PEP.");
        }

        throw new Error("No se pudo generar el PEP.");
      }

      const blob = await resp.blob();
      const filename = getDownloadFilename(resp) || lastPreview.output_filename || "PEP.docx";

      triggerDownload(blob, filename);
      showOk("PEP download started.");
    } catch (err) {
      showError(err?.message || "No se pudo generar el PEP.");
    } finally {
      setOverlay(false);
      if (generatePepBtn) generatePepBtn.disabled = false;
    }
  }

  function getDownloadFilename(resp) {
    const headerFilename = resp.headers.get("X-PEP-Filename");
    if (headerFilename) return headerFilename;

    const cd = resp.headers.get("Content-Disposition") || "";
    const match = cd.match(/filename="([^"]+)"/i);

    return match?.[1] || null;
  }

  function triggerDownload(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");

    a.href = url;
    a.download = filename || "PEP.docx";

    document.body.appendChild(a);
    a.click();
    a.remove();

    window.URL.revokeObjectURL(url);
  }

  if (previewBtn) {
    previewBtn.addEventListener("click", requestPreview);
  }
  if (papInfoBtn) {
      papInfoBtn.addEventListener("click", openPapInfoModal);
    }

    if (pddInfoBtn) {
      pddInfoBtn.addEventListener("click", openPddInfoModal);
    }

  if (generatePepBtn) {
    generatePepBtn.addEventListener("click", generatePep);
  }

  if (viewJsonBtn) {
    viewJsonBtn.addEventListener("click", openJsonModal);
  }

  if (selectReqBtn) {
    selectReqBtn.addEventListener("click", openRequirementsModal);
  }

  if (papInput) {
    papInput.addEventListener("change", resetPreview);
  }

  if (pddInput) {
    pddInput.addEventListener("change", resetPreview);
  }
  

  resetPreview();
});