document.addEventListener("DOMContentLoaded", () => {
  const elements = {
    form: document.getElementById("pepForm"),
    papInput: document.getElementById("id_pap_document"),
    pddInput: document.getElementById("id_pdd_document"),
    papFileName: document.getElementById("papFileName"),
    pddFileName: document.getElementById("pddFileName"),
    papDropZone: document.getElementById("papDropZone"),
    pddDropZone: document.getElementById("pddDropZone"),
    previewBtn: document.getElementById("previewBtn"),
    generatePepBtn: document.getElementById("generatePepBtn"),
    papInfoBtn: document.getElementById("papInfoBtn"),
    pddInfoBtn: document.getElementById("pddInfoBtn"),
    viewJsonBtn: document.getElementById("viewJsonBtn"),
    viewRequirementsBtn: document.getElementById("viewRequirementsBtn"),
    previewCard: document.getElementById("pepPreviewCard"),
    pepFilename: document.getElementById("pepFilename"),
    pepExecutionCost: document.getElementById("pepExecutionCost"),
    pepProjectName: document.getElementById("pepProjectName"),
    pepProjectId: document.getElementById("pepProjectId"),
    pepClient: document.getElementById("pepClient"),
    pepTechnology: document.getElementById("pepTechnology"),
    pepDetectionType: document.getElementById("pepDetectionType"),
    pepReqTotal: document.getElementById("pepReqTotal"),
    pepTechnologyJustification: document.getElementById(
      "pepTechnologyJustification"
    ),
    pepTechnologyJustificationText: document.getElementById(
      "pepTechnologyJustificationText"
    ),
    warningsBox: document.getElementById("pepWarnings"),
    warningsList: document.getElementById("pepWarningsList"),
    pepInputProjection: document.getElementById("pepInputProjection"),
    pepProcessName: document.getElementById("pepProcessName"),
    pepProcessFrequency: document.getElementById("pepProcessFrequency"),
pepNormalVolume: document.getElementById("pepNormalVolume"),
pepStressVolume: document.getElementById("pepStressVolume"),
pepDevelopmentPhase1: document.getElementById("pepDevelopmentPhase1"),
    pepDevelopmentPhase2: document.getElementById("pepDevelopmentPhase2"),
    pepDevelopmentPhase3: document.getElementById("pepDevelopmentPhase3"),
    pepDeploymentChange: document.getElementById("pepDeploymentChange"),
    pepDeploymentSame: document.getElementById("pepDeploymentSame"),
    pepCalculationCriterion: document.getElementById(
      "pepCalculationCriterion"
    ),
    pepCalculationCriterionText: document.getElementById(
      "pepCalculationCriterionText"
    ),
    pepInputProjectionError: document.getElementById(
      "pepInputProjectionError"
    ),
    pepInputProjectionErrorMessage: document.getElementById(
      "pepInputProjectionErrorMessage"
    ),
    pepMissingInputData: document.getElementById("pepMissingInputData"),
    pepMissingInputDataList: document.getElementById(
      "pepMissingInputDataList"
    ),
    overlay: document.getElementById("overlay"),
    overlayTitle: document.getElementById("overlayTitle"),
    progressText: document.getElementById("progressText"),
  };

  const ANALYZER_MESSAGE_TRANSLATIONS = new Map([
    [
      (
        "No se detectó un periodo máximo válido. El periodo normal se utilizó "
        + "como base para las pruebas al 50% y para los cálculos de estrés al 120%."
      ),
      (
        "No valid maximum activity period was detected. The normal period was "
        + "used as the baseline for 50% verification tests and 120% stress calculations."
      ),
    ],
    [
    (
      "Para Deployment/UAT se considera el 120% con insumos productivos "
      + "y entorno productivo. La diferencia aplica cuando cambia el tipo "
      + "de insumos o el entorno utilizado para la ejecución."
    ),
    (
      "For Deployment/UAT, 120% is considered using productive inputs "
      + "and a productive environment. The difference applies when the "
      + "input type or execution environment changes."
    ),
  ],
    [
      (
        "El campo 'Período de máxima actividad(es)' está documentado como 'TBD' "
        + "en el PDD, por lo que se trató como null. Se utilizó el periodo normal "
        + "como base de estrés."
      ),
      (
        'The "Maximum activity period(s)" field is marked as "TBD" in the PDD. '
        + "The normal period was used as the stress-test baseline."
      ),
    ],
    [
      (
        "El campo 'Volumen de transacciones durante el periodo de máxima actividad(es)' "
        + "está documentado como 'TBD' en el PDD, por lo que se trató como null."
      ),
      (
        'The "Transaction volume during the maximum activity period(s)" field is '
        + 'marked as "TBD" in the PDD and was not available for analysis.'
      ),
    ],
    [
      (
        "El campo 'Tiempo de ejecución manual del proceso' está documentado como 'TBD' "
        + "y no fue considerado en los cálculos."
      ),
      (
        'The "Manual process execution time" field is marked as "TBD" and was '
        + "not included in the calculations."
      ),
    ],
  ]);

  const SUPPORTED_FILE_EXTENSIONS = new Set(["pdf", "docx"]);

  const EMPTY_OPTIONAL_VALUES = new Set([
    "-",
    "null",
    "none",
    "n/a",
    "na",
    "not available",
  ]);

  const UNIT_TRANSLATIONS = new Map([
    ["archivo", "file"],
    ["archivos", "files"],
    ["caso", "case"],
    ["casos", "cases"],
    ["documento", "document"],
    ["documentos", "documents"],
    ["elemento", "item"],
    ["elementos", "items"],
    ["factura", "invoice"],
    ["facturas", "invoices"],
    ["orden", "order"],
    ["órdenes", "orders"],
    ["ordenes", "orders"],
    ["registro", "record"],
    ["registros", "records"],
    ["solicitud", "request"],
    ["solicitudes", "requests"],
    ["transacción", "transaction"],
    ["transacciones", "transactions"],
  ]);

  let lastPreview = null;

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

    if (parts.length === 2) {
      return parts.pop().split(";").shift();
    }

    return "";
  }

  function showOk(message) {
    Toast.fire({
      icon: "success",
      title: message,
    });
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

  function setText(element, value, fallback = "-") {
    if (!element) {
      return;
    }

    const text = String(value ?? "").trim();
    element.textContent = text || fallback;
  }

  function getOptionalText(value) {
    const text = String(value ?? "").trim();

    if (!text || EMPTY_OPTIONAL_VALUES.has(text.toLowerCase())) {
      return "";
    }

    return text;
  }

  function translateAnalyzerMessage(value) {
    const text = String(value ?? "").trim();

    if (!text) {
      return "";
    }

    return ANALYZER_MESSAGE_TRANSLATIONS.get(text) || text;
  }

  function setOverlay(on, title, text) {
    if (!elements.overlay) {
      return;
    }

    elements.overlay.classList.toggle("show", on);
    elements.overlay.setAttribute("aria-hidden", on ? "false" : "true");
    document.body.classList.toggle("is-processing", on);

    if (elements.form) {
      elements.form.setAttribute("aria-busy", on ? "true" : "false");
    }

    if (elements.overlayTitle && title) {
      elements.overlayTitle.textContent = title;
    }

    if (elements.progressText && text) {
      elements.progressText.textContent = text;
    }
  }

  function getFile(input) {
    return input?.files?.[0] || null;
  }

  function getFileExtension(file) {
    const fileName = String(file?.name || "");
    const extension = fileName.split(".").pop();

    return String(extension || "").trim().toLowerCase();
  }

  function isSupportedDocument(file) {
    return SUPPORTED_FILE_EXTENSIONS.has(getFileExtension(file));
  }

  function isFileDrag(event) {
    return Array.from(event.dataTransfer?.types || []).includes("Files");
  }

  function assignDroppedFile(input, file) {
    if (!input || !file) {
      return false;
    }

    try {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    } catch {
      return false;
    }
  }

  function setupFileDropZone({
    input,
    dropZone,
    documentLabel,
  }) {
    if (!input || !dropZone) {
      return;
    }

    let dragDepth = 0;

    function clearDragState() {
      dragDepth = 0;
      dropZone.classList.remove("is-dragover");
    }

    dropZone.addEventListener("dragenter", (event) => {
      if (!isFileDrag(event)) {
        return;
      }

      event.preventDefault();
      dragDepth += 1;
      dropZone.classList.add("is-dragover");
    });

    dropZone.addEventListener("dragover", (event) => {
      if (!isFileDrag(event)) {
        return;
      }

      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      dropZone.classList.add("is-dragover");
    });

    dropZone.addEventListener("dragleave", (event) => {
      if (!isFileDrag(event)) {
        return;
      }

      dragDepth = Math.max(0, dragDepth - 1);

      if (dragDepth === 0) {
        dropZone.classList.remove("is-dragover");
      }
    });

    dropZone.addEventListener("drop", (event) => {
      if (!isFileDrag(event)) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();
      clearDragState();

      const droppedFiles = Array.from(event.dataTransfer?.files || []);

      if (droppedFiles.length !== 1) {
        showError(`Drop one ${documentLabel} file at a time.`);
        return;
      }

      const [file] = droppedFiles;

      if (!isSupportedDocument(file)) {
        showError(`${documentLabel} must be a PDF or DOCX file.`);
        return;
      }

      if (!assignDroppedFile(input, file)) {
        showError(
          "This browser could not attach the dropped file. Use Choose file instead."
        );
      }
    });

    window.addEventListener("blur", clearDragState);
  }

  function preventBrowserFileNavigation(event) {
    if (isFileDrag(event)) {
      event.preventDefault();
    }
  }

  function updateFilePicker(input, fileNameElement) {
    if (!input || !fileNameElement) {
      return;
    }

    const file = getFile(input);
    const control = input.nextElementSibling;

    fileNameElement.textContent = file ? file.name : "No file selected";

    if (control?.classList.contains("pep-file-control")) {
      control.classList.toggle("has-file", Boolean(file));
    }
  }

  function resetPreview() {
    lastPreview = null;

    if (elements.previewCard) {
      elements.previewCard.hidden = true;
    }
  }

  function validateFiles() {
    const papFile = getFile(elements.papInput);
    const pddFile = getFile(elements.pddInput);

    if (!papFile) {
      throw new Error("Upload the PAP document before starting the analysis.");
    }

    if (!isSupportedDocument(papFile)) {
      throw new Error("The PAP document must be a PDF or DOCX file.");
    }

    if (!pddFile) {
      throw new Error("Upload the PDD/FDD document before starting the analysis.");
    }

    if (!isSupportedDocument(pddFile)) {
      throw new Error("The PDD/FDD document must be a PDF or DOCX file.");
    }

    return {
      papFile,
      pddFile,
    };
  }

  function buildFormData() {
    const { papFile, pddFile } = validateFiles();
    const formData = new FormData();

    formData.set("pap_document", papFile, papFile.name);
    formData.set("pdd_document", pddFile, pddFile.name);

    return formData;
  }

  function getRequirements() {
    const requirements = lastPreview?.pdd?.requerimientos;
    return Array.isArray(requirements) ? requirements : [];
  }

  function formatDetectionType(value) {
    const normalized = String(value || "").trim().toLowerCase();

    if (normalized === "explicita") {
      return "Explicit";
    }

    if (normalized === "inferida") {
      return "Inferred";
    }

    if (normalized === "no_encontrada") {
      return "Not detected";
    }

    return "";
  }

  function renderTechnologyDetection(value) {
    if (!elements.pepDetectionType) {
      return;
    }

    const detectionType = formatDetectionType(value);

    elements.pepDetectionType.textContent = detectionType || "-";
    elements.pepDetectionType.classList.remove(
      "pep-inline-status--warning",
      "pep-inline-status--error"
    );

    if (!detectionType || detectionType === "Explicit") {
      elements.pepDetectionType.hidden = true;
      return;
    }

    if (detectionType === "Inferred") {
      elements.pepDetectionType.classList.add("pep-inline-status--warning");
    }

    if (detectionType === "Not detected") {
      elements.pepDetectionType.classList.add("pep-inline-status--error");
    }

    elements.pepDetectionType.hidden = false;
  }

  function renderTechnologyJustification(justification) {
    if (
      !elements.pepTechnologyJustification
      || !elements.pepTechnologyJustificationText
    ) {
      return;
    }

    const text = getOptionalText(justification);

    if (!text) {
      elements.pepTechnologyJustification.hidden = true;
      elements.pepTechnologyJustificationText.textContent = "-";
      return;
    }

    elements.pepTechnologyJustificationText.textContent = text;
    elements.pepTechnologyJustification.hidden = false;
  }

  function formatExecutionCost(cost = {}) {
    const formattedCost = getOptionalText(cost.total_usd_formatted);
    const currency = getOptionalText(cost.currency).toUpperCase() || "USD";

    if (formattedCost) {
      return `${formattedCost} ${currency}`;
    }

    const totalCost = Number(cost.total_usd);

    if (!Number.isFinite(totalCost)) {
      return "Not available";
    }

    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency,
        minimumFractionDigits: 4,
        maximumFractionDigits: 6,
      }).format(totalCost);
    } catch {
      return `${totalCost.toFixed(4)} ${currency}`;
    }
  }

  function formatUnit(unit) {
    const cleanUnit = String(unit || "").trim();

    if (!cleanUnit) {
      return "";
    }

    return UNIT_TRANSLATIONS.get(cleanUnit.toLowerCase()) || cleanUnit;
  }

  function formatInputQuantity(quantity, unit) {
    const numericQuantity = Number(quantity);

    if (!Number.isFinite(numericQuantity)) {
      return "-";
    }

    const formattedQuantity = new Intl.NumberFormat("en-US").format(
      numericQuantity
    );
    const formattedUnit = formatUnit(unit);

    return formattedUnit
      ? `${formattedQuantity} ${formattedUnit}`
      : formattedQuantity;
  }

  function formatMissingField(value) {
    const fields = {
      descripcion_breve_proceso: "Process description",
      calendario_frecuencia: "Process frequency",
      "cantidad_periodo_normal.cantidad": "Normal period quantity",
    };

    return fields[value] || value;
  }

  function resetInputProjection() {
    if (elements.pepInputProjection) {
      elements.pepInputProjection.hidden = true;
    }

    if (elements.pepInputProjectionError) {
      elements.pepInputProjectionError.hidden = true;
    }

    if (elements.pepMissingInputData) {
      elements.pepMissingInputData.hidden = true;
    }

    if (elements.pepMissingInputDataList) {
      elements.pepMissingInputDataList.innerHTML = "";
    }

    if (elements.pepCalculationCriterion) {
      elements.pepCalculationCriterion.hidden = true;
    }
  }

  function renderCalculationCriterion(criterion) {
    if (
      !elements.pepCalculationCriterion
      || !elements.pepCalculationCriterionText
    ) {
      return;
    }

    const text = translateAnalyzerMessage(criterion);

    if (!text) {
      elements.pepCalculationCriterion.hidden = true;
      elements.pepCalculationCriterionText.textContent = "-";
      return;
    }

    elements.pepCalculationCriterionText.textContent = text;
    elements.pepCalculationCriterion.hidden = false;
  }

  function renderInputProjectionError(calculation = {}) {
    if (elements.pepInputProjectionErrorMessage) {
      const message = translateAnalyzerMessage(
        calculation.mensaje_validacion
      );

      elements.pepInputProjectionErrorMessage.textContent = (
        message || "The testing input plan could not be calculated."
      );
    }

    const missingFields = Array.isArray(calculation.datos_faltantes)
      ? calculation.datos_faltantes
      : [];

    if (elements.pepMissingInputDataList && missingFields.length) {
      elements.pepMissingInputDataList.innerHTML = "";

      for (const field of missingFields) {
        const listItem = document.createElement("li");
        listItem.textContent = formatMissingField(field);
        elements.pepMissingInputDataList.appendChild(listItem);
      }

      if (elements.pepMissingInputData) {
        elements.pepMissingInputData.hidden = false;
      }
    }

    if (elements.pepInputProjectionError) {
      elements.pepInputProjectionError.hidden = false;
    }
  }

  function renderInputProjection(pdd) {
    resetInputProjection();

    const calculation = pdd?.calculo_insumos || {};
    const context = pdd?.contexto_proceso || {};

    if (calculation.estado_calculo === "error_validacion") {
      renderInputProjectionError(calculation);
      return;
    }

    const plan = calculation.plan_insumos;

    if (!plan) {
      renderInputProjectionError({
        mensaje_validacion: (
          "No testing input plan was returned for this document analysis."
        ),
        datos_faltantes: calculation.datos_faltantes || [],
      });
      return;
    }

    setText(
      elements.pepProcessName,
      plan.nombre_proceso || context.descripcion_breve_proceso
    );
    setText(
      elements.pepProcessFrequency,
      plan.frecuencia || context.calendario_frecuencia
    );

    if (elements.pepNormalVolume) {
      elements.pepNormalVolume.textContent = formatInputQuantity(
        plan.insumos_base_periodo_normal,
        plan.unidad_elemento
      );
    }

    if (elements.pepStressVolume) {
  elements.pepStressVolume.textContent = formatInputQuantity(
    plan.insumos_estres_120,
    plan.unidad_elemento
  );
}

    if (elements.pepDevelopmentPhase1) {
      elements.pepDevelopmentPhase1.textContent = formatInputQuantity(
        plan.development?.fase_1?.cantidad,
        plan.unidad_elemento
      );
    }

    if (elements.pepDevelopmentPhase2) {
      elements.pepDevelopmentPhase2.textContent = formatInputQuantity(
        plan.development?.fase_2?.cantidad,
        plan.unidad_elemento
      );
    }

    if (elements.pepDevelopmentPhase3) {
      elements.pepDevelopmentPhase3.textContent = formatInputQuantity(
        plan.development?.fase_3?.cantidad,
        plan.unidad_elemento
      );
    }

if (elements.pepDeploymentChange) {
  const deploymentMetric = elements.pepDeploymentChange.closest(".metric");
  const deploymentLabel = deploymentMetric?.querySelector(".metric-label");

  if (deploymentLabel) {
    deploymentLabel.textContent = (
      "Deployment / UAT · Productive inputs and productive environment · 120%"
    );
  }

  elements.pepDeploymentChange.textContent = formatInputQuantity(
    plan.deployment?.uat_productivo?.cantidad,
    plan.unidad_elemento
  );
}

if (elements.pepDeploymentSame) {
  const oldDeploymentMetric = elements.pepDeploymentSame.closest(".metric");

  if (oldDeploymentMetric) {
    oldDeploymentMetric.hidden = true;
  }
}

    renderCalculationCriterion(
  [
    plan.criterio_calculo,
    plan.nota_deployment,
  ]
    .filter(Boolean)
    .join(" ")
);

    if (elements.pepInputProjection) {
      elements.pepInputProjection.hidden = false;
    }
  }

  function renderWarnings(warnings) {
    if (!elements.warningsBox || !elements.warningsList) {
      return;
    }

    elements.warningsList.innerHTML = "";

    if (!Array.isArray(warnings) || warnings.length === 0) {
      elements.warningsBox.hidden = true;
      return;
    }

    const uniqueWarnings = [...new Set(
      warnings
        .map((warning) => translateAnalyzerMessage(warning))
        .filter(Boolean)
    )];

    for (const warning of uniqueWarnings) {
      const listItem = document.createElement("li");
      listItem.textContent = warning;
      elements.warningsList.appendChild(listItem);
    }

    elements.warningsBox.hidden = uniqueWarnings.length === 0;
  }

  function moveFocusToResults() {
    if (!elements.previewCard) {
      return;
    }

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    elements.previewCard.focus({
      preventScroll: true,
    });

    elements.previewCard.scrollIntoView({
      behavior: prefersReducedMotion ? "auto" : "smooth",
      block: "start",
    });
  }

  function renderPreview(data) {
    lastPreview = data;

    const pap = data?.pap || {};
    const pdd = data?.pdd || {};
    const technology = pdd.tecnologia || {};
    const requirements = Array.isArray(pdd.requerimientos)
      ? pdd.requerimientos
      : [];

    setText(elements.pepFilename, data.output_filename, "PEP.docx");
    setText(elements.pepExecutionCost, formatExecutionCost(data.cost));
    setText(elements.pepProjectName, pap.nombre_proyecto);
    setText(elements.pepProjectId, data.project_id || pap.id_proyecto);
    setText(elements.pepClient, pap.nombre_cliente);
    setText(elements.pepTechnology, technology.valor);
    setText(elements.pepReqTotal, requirements.length, "0");

    renderTechnologyDetection(technology.tipo_deteccion);
    renderTechnologyJustification(technology.justificacion);
    renderInputProjection(pdd);
    renderWarnings(data.warnings || []);

    if (elements.previewCard) {
      elements.previewCard.hidden = false;
      moveFocusToResults();
    }
  }

  function openRequirementsModal() {
    const requirements = getRequirements();

    if (!requirements.length) {
      showError("No functional requirements were detected.");
      return;
    }

    const requirementItems = requirements
      .map((requirement) => (
        `<li>${escapeHtml(requirement)}</li>`
      ))
      .join("");

    Swal.fire({
      title: "Functional requirements",
      html: `
        <div class="pep-modal-copy">
          <p>
            ${requirements.length} main functional requirement${
              requirements.length === 1 ? "" : "s"
            } detected in the PDD/FDD.
          </p>
          <ol class="pep-requirements-list">
            ${requirementItems}
          </ol>
        </div>
      `,
      width: "min(820px, 94vw)",
      confirmButtonText: "Close",
      allowOutsideClick: true,
      allowEscapeKey: true,
    });
  }

  function openJsonModal() {
    if (!lastPreview) {
      showError("Analyze the documents before viewing technical details.");
      return;
    }

    const prettyJson = JSON.stringify(lastPreview, null, 2);

    Swal.fire({
      title: "Technical execution data",
      html: `
        <pre class="pep-json-preview">${escapeHtml(prettyJson)}</pre>
      `,
      width: "min(1100px, 94vw)",
      showCancelButton: true,
      confirmButtonText: "Copy JSON",
      cancelButtonText: "Close",
      allowOutsideClick: true,
      allowEscapeKey: true,
    }).then(async (result) => {
      if (!result.isConfirmed) {
        return;
      }

      try {
        await navigator.clipboard.writeText(prettyJson);
        showOk("JSON copied to clipboard.");
      } catch {
        showError("The JSON could not be copied to the clipboard.");
      }
    });
  }

  function openPapInfoModal() {
  Swal.fire({
    icon: "info",
    title: "PAP document requirements",
    html: `
      <div class="pep-modal-copy">
        <p class="pep-modal-subtitle">
          Project Administration Plan (PAP)
        </p>

        <p>
          The PAP provides the administrative and technical
          information required to complete the PEP.
        </p>

        <h3>Functional scope</h3>
        <ul>
          <li>Project identification and client information.</li>
          <li>Project team information.</li>
          <li>Software and hardware requirements.</li>
        </ul>

        <h3>Required content</h3>
        <ul>
          <li>Project name, project ID, and client name.</li>
          <li>Project roles and responsible people.</li>
          <li>Software requirements.</li>
          <li>Hardware requirements.</li>
        </ul>

        <h3>Important</h3>
        <ul>
          <li>The analyzer does not invent missing information.</li>
<li>
  Technology is identified from the PDD/FDD document.
</li>
          <li>Missing information can be reported for review.</li>
        </ul>
      </div>
    `,
    confirmButtonText: "Close",
    width: "min(760px, 92vw)",
  });
}

  function openPddInfoModal() {
  Swal.fire({
    icon: "info",
    title: "PDD/FDD document requirements",
    html: `
      <div class="pep-modal-copy">
        <p class="pep-modal-subtitle">
          Process Definition Document (PDD) /
          Functional Design Document (FDD)
        </p>

        <p>
          The PDD/FDD is analyzed to identify the main
          functional requirements and calculate the testing
          input plan.
        </p>

        <h3>Functional scope</h3>
        <ul>
          <li>
            Main functional requirements or future-process steps.
          </li>
          <li>
            Parent functional requirements are identified as the
            main testing scope.
          </li>
          <li>
            Internal substeps and subordinate requirements are excluded
            from the main requirement list.
          </li>
        </ul>

        <h3>Required content</h3>
        <ul>
          <li>
            A functional requirements, process steps, or equivalent
            functional section.
          </li>
          <li>
            Technology used to build the flow, automation,
            or application.
          </li>
          <li>Brief process description.</li>
          <li>Process calendar or execution frequency.</li>
          <li>Normal-period transaction volume.</li>
        </ul>
          
        <h3>Important</h3>
        <ul>
          <li>
            Main detected requirements are included automatically
            in the PEP.
          </li>
          <li>
            Maximum-activity volume is optional. When available,
            it is used as the stress calculation baseline.
          </li>
          <li>
            If mandatory input planning data is missing, the testing
            input plan cannot be calculated.
          </li>
        </ul>
      </div>
    `,
    confirmButtonText: "Close",
    width: "min(760px, 92vw)",
  });
}

  async function requestPreview() {
    if (!elements.form) {
      return;
    }

    const previewUrl = elements.form.dataset.previewUrl;

    if (!previewUrl) {
      showError("The preview URL is not configured.");
      return;
    }

    try {
      const formData = buildFormData();
      const csrf = getCookie("csrftoken");

      setOverlay(
        true,
        "Analyzing documents",
        (
          "Extracting project data, technology, functional requirements, "
          + "and testing input information. Keep this tab open."
        )
      );

      if (elements.previewBtn) {
        elements.previewBtn.disabled = true;
      }

      const response = await fetch(previewUrl, {
        method: "POST",
        body: formData,
        headers: {
          "X-CSRFToken": csrf,
        },
        credentials: "same-origin",
      });

      const data = await response.json().catch(() => null);

      if (!response.ok || !data || data.ok === false) {
        throw new Error(
          translateAnalyzerMessage(data?.message)
          || "The document analysis could not be completed."
        );
      }

      renderPreview(data);
      showOk("Document analysis completed.");
    } catch (error) {
      showError(
        translateAnalyzerMessage(error?.message)
        || "The document analysis could not be completed."
      );
    } finally {
      setOverlay(false);

      if (elements.previewBtn) {
        elements.previewBtn.disabled = false;
      }
    }
  }

  async function generatePep() {
    if (!elements.form) {
      return;
    }

    const generateUrl = elements.form.dataset.generateUrl;

    if (!generateUrl) {
      showError("The generation URL is not configured.");
      return;
    }

    if (!lastPreview) {
      showError("Analyze the documents before generating the PEP.");
      return;
    }

    try {
      const formData = buildFormData();
      const csrf = getCookie("csrftoken");

      setOverlay(
        true,
        "Generating PEP",
        "Building the final DOCX document. Keep this tab open."
      );

      if (elements.generatePepBtn) {
        elements.generatePepBtn.disabled = true;
      }

      const response = await fetch(generateUrl, {
        method: "POST",
        body: formData,
        headers: {
          "X-CSRFToken": csrf,
        },
        credentials: "same-origin",
      });

      if (!response.ok) {
        const contentType = (
          response.headers.get("content-type") || ""
        ).toLowerCase();

        if (contentType.includes("application/json")) {
          const data = await response.json().catch(() => null);

          throw new Error(
            translateAnalyzerMessage(data?.message)
            || "The PEP could not be generated."
          );
        }

        throw new Error("The PEP could not be generated.");
      }

      const blob = await response.blob();
      const filename = (
        getDownloadFilename(response)
        || lastPreview.output_filename
        || "PEP.docx"
      );

      triggerDownload(blob, filename);
      showOk("PEP download started.");
    } catch (error) {
      showError(
        translateAnalyzerMessage(error?.message)
        || "The PEP could not be generated."
      );
    } finally {
      setOverlay(false);

      if (elements.generatePepBtn) {
        elements.generatePepBtn.disabled = false;
      }
    }
  }

  function getDownloadFilename(response) {
    const headerFilename = response.headers.get("X-PEP-Filename");

    if (headerFilename) {
      return headerFilename;
    }

    const contentDisposition = response.headers.get(
      "Content-Disposition"
    ) || "";

    const utf8Match = contentDisposition.match(
      /filename\*=UTF-8''([^;]+)/i
    );

    if (utf8Match?.[1]) {
      try {
        return decodeURIComponent(utf8Match[1]);
      } catch {
        return utf8Match[1];
      }
    }

    const filenameMatch = contentDisposition.match(
      /filename="([^"]+)"/i
    );

    return filenameMatch?.[1] || null;
  }

  function triggerDownload(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = filename || "PEP.docx";

    document.body.appendChild(link);
    link.click();
    link.remove();

    window.setTimeout(() => {
      window.URL.revokeObjectURL(url);
    }, 1000);
  }

  document.addEventListener("dragover", preventBrowserFileNavigation);
  document.addEventListener("drop", preventBrowserFileNavigation);

  setupFileDropZone({
    input: elements.papInput,
    dropZone: elements.papDropZone,
    documentLabel: "PAP document",
  });

  setupFileDropZone({
    input: elements.pddInput,
    dropZone: elements.pddDropZone,
    documentLabel: "PDD/FDD document",
  });

  elements.form?.addEventListener("submit", (event) => {
    event.preventDefault();
    requestPreview();
  });

  elements.papInfoBtn?.addEventListener("click", openPapInfoModal);
  elements.pddInfoBtn?.addEventListener("click", openPddInfoModal);
  elements.generatePepBtn?.addEventListener("click", generatePep);
  elements.viewJsonBtn?.addEventListener("click", openJsonModal);
  elements.viewRequirementsBtn?.addEventListener(
    "click",
    openRequirementsModal
  );

  elements.papInput?.addEventListener("change", () => {
    updateFilePicker(elements.papInput, elements.papFileName);
    resetPreview();
  });

  elements.pddInput?.addEventListener("change", () => {
    updateFilePicker(elements.pddInput, elements.pddFileName);
    resetPreview();
  });

  updateFilePicker(elements.papInput, elements.papFileName);
  updateFilePicker(elements.pddInput, elements.pddFileName);
  resetPreview();
});

