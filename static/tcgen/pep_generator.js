document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("pepForm");
  const papInput = document.getElementById("id_pap_document");
  const pddInput = document.getElementById("id_pdd_document");

  const previewBtn = document.getElementById("previewBtn");
  const generatePepBtn = document.getElementById("generatePepBtn");
  const papInfoBtn = document.getElementById("papInfoBtn");
  const pddInfoBtn = document.getElementById("pddInfoBtn");
  const viewJsonBtn = document.getElementById("viewJsonBtn");
  const viewRequirementsBtn = document.getElementById(
    "viewRequirementsBtn"
  );

  const previewCard = document.getElementById("pepPreviewCard");
  const pepFilename = document.getElementById("pepFilename");
  const pepProjectId = document.getElementById("pepProjectId");
  const pepClient = document.getElementById("pepClient");
  const pepTechnology = document.getElementById("pepTechnology");
  const pepDetectionType = document.getElementById("pepDetectionType");
  const pepFilenameMetric = document.getElementById(
    "pepFilenameMetric"
  );
  const pepCost = document.getElementById("pepCost");
  const pepReqTotal = document.getElementById("pepReqTotal");

  const pepTechnologyJustification = document.getElementById(
    "pepTechnologyJustification"
  );
  const pepTechnologyJustificationText = document.getElementById(
    "pepTechnologyJustificationText"
  );

  const warningsBox = document.getElementById("pepWarnings");
  const warningsList = document.getElementById("pepWarningsList");

  const pepInputProjection = document.getElementById(
    "pepInputProjection"
  );
  const pepProcessName = document.getElementById("pepProcessName");
  const pepProcessFrequency = document.getElementById(
    "pepProcessFrequency"
  );
  const pepNormalVolume = document.getElementById("pepNormalVolume");
  const pepStressVolume = document.getElementById("pepStressVolume");

  const pepDevelopmentPhase1 = document.getElementById(
    "pepDevelopmentPhase1"
  );
  const pepDevelopmentPhase2 = document.getElementById(
    "pepDevelopmentPhase2"
  );
  const pepDevelopmentPhase3 = document.getElementById(
    "pepDevelopmentPhase3"
  );

  const pepDeploymentChange = document.getElementById(
    "pepDeploymentChange"
  );
  const pepDeploymentSame = document.getElementById(
    "pepDeploymentSame"
  );

  const pepCalculationCriterion = document.getElementById(
    "pepCalculationCriterion"
  );
  const pepCalculationCriterionText = document.getElementById(
    "pepCalculationCriterionText"
  );

  const pepInputProjectionError = document.getElementById(
    "pepInputProjectionError"
  );
  const pepInputProjectionErrorMessage = document.getElementById(
    "pepInputProjectionErrorMessage"
  );
  const pepMissingInputData = document.getElementById(
    "pepMissingInputData"
  );
  const pepMissingInputDataList = document.getElementById(
    "pepMissingInputDataList"
  );

  const overlay = document.getElementById("overlay");
  const overlayTitle = document.getElementById("overlayTitle");
  const progressText = document.getElementById("progressText");
  const progressBar = document.getElementById("progressBar");

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


  function setOverlay(
    on,
    title,
    text,
    percent
  ) {
    if (!overlay) {
      return;
    }

    overlay.classList.toggle("show", on);
    overlay.setAttribute(
      "aria-hidden",
      on ? "false" : "true"
    );

    if (overlayTitle && title) {
      overlayTitle.textContent = title;
    }

    if (progressText && text) {
      progressText.textContent = text;
    }

    if (progressBar) {
      progressBar.style.width = `${percent || 0}%`;
    }
  }


function resetPreview() {
  lastPreview = null;

  if (previewCard) {
    previewCard.style.display = "none";
  }
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

    return {
      papFile,
      pddFile,
    };
  }


  function buildFormData() {
  const {
    papFile,
    pddFile,
  } = validateFiles();

  const formData = new FormData();

  formData.set(
    "pap_document",
    papFile,
    papFile.name
  );

  formData.set(
    "pdd_document",
    pddFile,
    pddFile.name
  );

  return formData;
}


  function renderPreview(data) {
    lastPreview = data;

    const pap = data?.pap || {};
    const pdd = data?.pdd || {};
    const technology = pap.tecnologia || {};
    const requirements = Array.isArray(pdd.requerimientos)
      ? pdd.requerimientos
      : [];

    if (pepFilename) {
      pepFilename.textContent =
        data.output_filename || "PEP.docx";
    }

    if (pepFilenameMetric) {
      pepFilenameMetric.textContent =
        data.output_filename || "PEP.docx";
    }

    if (pepProjectId) {
      pepProjectId.textContent =
        data.project_id || "-";
    }

    if (pepClient) {
      pepClient.textContent =
        pap.nombre_cliente || "-";
    }

    if (pepTechnology) {
      pepTechnology.textContent =
        technology.valor || "-";
    }

    if (pepDetectionType) {
      pepDetectionType.textContent =
        formatDetectionType(
          technology.tipo_deteccion
        );
    }

    if (pepCost) {
      pepCost.textContent =
        data.cost?.total_usd_formatted || "$0.00";
    }

    if (pepReqTotal) {
      pepReqTotal.textContent =
        String(requirements.length);
    }

    renderTechnologyJustification(
      technology.justificacion
    );

    renderInputProjection(
      pdd
    );

    renderWarnings(
      data.warnings || []
    );

    if (previewCard) {
      previewCard.style.display = "block";
    }
  }


  function formatDetectionType(value) {
    const normalized = String(value || "")
      .trim()
      .toLowerCase();

    if (normalized === "explicita") {
      return "Explicit";
    }

    if (normalized === "inferida") {
      return "Inferred";
    }

    if (normalized === "no_encontrada") {
      return "Not found";
    }

    return "-";
  }


  function renderTechnologyJustification(
    justification
  ) {
    if (
      !pepTechnologyJustification
      || !pepTechnologyJustificationText
    ) {
      return;
    }

    const text = String(
      justification || ""
    ).trim();

    if (!text) {
      pepTechnologyJustification.hidden = true;
      pepTechnologyJustificationText.textContent = "-";
      return;
    }

    pepTechnologyJustificationText.textContent = text;
    pepTechnologyJustification.hidden = false;
  }

  function resetInputProjection() {
    if (pepInputProjection) {
      pepInputProjection.hidden = true;
    }

    if (pepInputProjectionError) {
      pepInputProjectionError.hidden = true;
    }

    if (pepMissingInputData) {
      pepMissingInputData.hidden = true;
    }

    if (pepMissingInputDataList) {
      pepMissingInputDataList.innerHTML = "";
    }
  }


  function renderInputProjection(pdd) {
    resetInputProjection();

    const calculation =
      pdd?.calculo_insumos || {};

    const context =
      pdd?.contexto_proceso || {};

    if (
      calculation.estado_calculo
      === "error_validacion"
    ) {
      renderInputProjectionError(
        calculation
      );

      return;
    }

    const plan = calculation.plan_insumos;

    if (!plan) {
      return;
    }

    if (pepProcessName) {
      pepProcessName.textContent =
        plan.nombre_proceso
        || context.descripcion_breve_proceso
        || "-";
    }

    if (pepProcessFrequency) {
      pepProcessFrequency.textContent =
        plan.frecuencia
        || context.calendario_frecuencia
        || "-";
    }

    if (pepNormalVolume) {
      pepNormalVolume.textContent =
        formatInputQuantity(
          plan.insumos_base_periodo_normal,
          plan.unidad_elemento
        );
    }

    if (pepStressVolume) {
      pepStressVolume.textContent =
        formatInputQuantity(
          plan.insumos_estres_120,
          plan.unidad_elemento
        );
    }

    if (pepDevelopmentPhase1) {
      pepDevelopmentPhase1.textContent =
        formatInputQuantity(
          plan.development?.fase_1?.cantidad,
          plan.unidad_elemento
        );
    }

    if (pepDevelopmentPhase2) {
      pepDevelopmentPhase2.textContent =
        formatInputQuantity(
          plan.development?.fase_2?.cantidad,
          plan.unidad_elemento
        );
    }

    if (pepDevelopmentPhase3) {
      pepDevelopmentPhase3.textContent =
        formatInputQuantity(
          plan.development?.fase_3?.cantidad,
          plan.unidad_elemento
        );
    }

    if (pepDeploymentChange) {
      pepDeploymentChange.textContent =
        formatInputQuantity(
          plan.deployment
            ?.cambio_entorno_o_insumos
            ?.cantidad,
          plan.unidad_elemento
        );
    }

    if (pepDeploymentSame) {
      pepDeploymentSame.textContent =
        formatInputQuantity(
          plan.deployment
            ?.mismo_entorno_e_insumos
            ?.cantidad,
          plan.unidad_elemento
        );
    }

    renderCalculationCriterion(
      plan.criterio_calculo
    );

    if (pepInputProjection) {
      pepInputProjection.hidden = false;
    }
  }


  function renderInputProjectionError(
    calculation
  ) {
    if (pepInputProjectionErrorMessage) {
      pepInputProjectionErrorMessage.textContent =
        calculation.mensaje_validacion
        || (
          "The testing input projection could "
          + "not be calculated."
        );
    }

    const missingFields = Array.isArray(
      calculation.datos_faltantes
    )
      ? calculation.datos_faltantes
      : [];

    if (
      pepMissingInputDataList
      && missingFields.length
    ) {
      pepMissingInputDataList.innerHTML = "";

      for (const field of missingFields) {
        const listItem =
          document.createElement("li");

        listItem.textContent =
          formatMissingField(field);

        pepMissingInputDataList.appendChild(
          listItem
        );
      }

      if (pepMissingInputData) {
        pepMissingInputData.hidden = false;
      }
    }

    if (pepInputProjectionError) {
      pepInputProjectionError.hidden = false;
    }
  }


  function formatMissingField(value) {
    const fields = {
      descripcion_breve_proceso:
        "Process description",
      calendario_frecuencia:
        "Process frequency",
      "cantidad_periodo_normal.cantidad":
        "Normal period quantity",
    };

    return fields[value] || value;
  }


  function formatInputQuantity(
    quantity,
    unit
  ) {
    const numericQuantity = Number(quantity);

    if (!Number.isFinite(numericQuantity)) {
      return "-";
    }

    const formattedQuantity =
      new Intl.NumberFormat("en-US").format(
        numericQuantity
      );

    const cleanUnit = String(
      unit || ""
    ).trim();

    if (!cleanUnit) {
      return formattedQuantity;
    }

    return `${formattedQuantity} ${cleanUnit}`;
  }


  function renderCalculationCriterion(
    criterion
  ) {
    if (
      !pepCalculationCriterion
      || !pepCalculationCriterionText
    ) {
      return;
    }

    const text = String(
      criterion || ""
    ).trim();

    if (!text) {
      pepCalculationCriterion.hidden = true;
      pepCalculationCriterionText.textContent = "-";
      return;
    }

    pepCalculationCriterionText.textContent = text;
    pepCalculationCriterion.hidden = false;
  }


  function renderWarnings(warnings) {
    if (
      !warningsBox
      || !warningsList
    ) {
      return;
    }

    warningsList.innerHTML = "";

    if (
      !Array.isArray(warnings)
      || warnings.length === 0
    ) {
      warningsBox.hidden = true;
      return;
    }

    for (const warning of warnings) {
      const listItem =
        document.createElement("li");

      listItem.textContent = warning;

      warningsList.appendChild(
        listItem
      );
    }

    warningsBox.hidden = false;
  }


  function openJsonModal() {
    if (!lastPreview) {
      showError(
        "Primero genera la previsualización."
      );

      return;
    }

    const prettyJson = JSON.stringify(
      lastPreview,
      null,
      2
    );

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
      if (!result.isConfirmed) {
        return;
      }

      try {
        await navigator.clipboard.writeText(
          prettyJson
        );

        showOk(
          "JSON copied to clipboard."
        );
      } catch {
        showError(
          "No se pudo copiar el JSON."
        );
      }
    });
  }


  function openPapInfoModal() {
    Swal.fire({
      icon: "info",
      title: "PAP document requirements",
      html: `
        <div style="text-align:left; line-height:1.55;">
          <p>
            The PAP provides the administrative and technical
            information required to fill the PEP.
          </p>

          <p><strong>Recommended content:</strong></p>

          <ul>
            <li>Project name and project ID.</li>
            <li>Client name.</li>
            <li>
              Technology used to build the flow,
              automation or application.
            </li>
            <li>Project roles and responsible people.</li>
            <li>Software requirements.</li>
            <li>Hardware requirements.</li>
          </ul>

          <p><strong>Important:</strong></p>

          <ul>
            <li>
              The automation does not invent missing information.
            </li>
            <li>
              Technology may be explicit or inferred from
              document evidence.
            </li>
            <li>
              Missing information may be reported as a warning.
            </li>
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
            The PDD/FDD is analyzed to identify the main
            functional requirements and calculate the testing
            input projection.
          </p>

          <p><strong>Functional scope:</strong></p>

          <ul>
            <li>
              TO-BE actions, Process Steps or an equivalent
              functional section.
            </li>
            <li>
              Main functional requirements or identifiable
              process steps.
            </li>
            <li>
              Clear functional titles when available.
            </li>
          </ul>

          <p><strong>Input projection data:</strong></p>

          <ul>
            <li>Brief process description.</li>
            <li>Process calendar or execution frequency.</li>
            <li>Normal period transaction volume.</li>
            <li>
              Maximum activity volume when documented.
            </li>
          </ul>

          <p><strong>Important:</strong></p>

          <ul>
            <li>
              All main requirements detected are included
              automatically in the PEP.
            </li>
            <li>
              Subrequirements and internal steps are excluded
              when they belong to a parent requirement.
            </li>
            <li>
              If mandatory volume data is missing, the input
              projection will not be calculated.
            </li>
          </ul>
        </div>
      `,
      confirmButtonText: "Understood",
      width: "min(760px, 92vw)",
    });
  }


  async function requestPreview() {
    if (!form) {
      return;
    }

    const previewUrl =
      form.dataset.previewUrl;

    if (!previewUrl) {
      showError(
        "Preview URL is not configured."
      );

      return;
    }

    try {
      const formData = buildFormData();
      const csrf = getCookie("csrftoken");

      setOverlay(
        true,
        "Analyzing documents",
        (
          "Extracting PAP data, functional requirements "
          + "and testing input information..."
        ),
        35
      );

      if (previewBtn) {
        previewBtn.disabled = true;
      }

      const response = await fetch(
        previewUrl,
        {
          method: "POST",
          body: formData,
          headers: {
            "X-CSRFToken": csrf,
          },
          credentials: "same-origin",
        }
      );

      const data = await response
        .json()
        .catch(() => null);

      if (!response.ok) {
        throw new Error(
          data?.message
          || "No se pudo generar la previsualización."
        );
      }

      renderPreview(data);

      showOk(
        "Document analysis completed."
      );
    } catch (error) {
      showError(
        error?.message
        || "No se pudo generar la previsualización."
      );
    } finally {
      setOverlay(false);

      if (previewBtn) {
        previewBtn.disabled = false;
      }
    }
  }


  async function generatePep() {
    if (!form) {
      return;
    }

    const generateUrl =
      form.dataset.generateUrl;

    if (!generateUrl) {
      showError(
        "Generate URL is not configured."
      );

      return;
    }

    if (!lastPreview) {
      showError(
        "Primero genera la previsualización."
      );

      return;
    }

    try {
      const formData = buildFormData();
      const csrf = getCookie("csrftoken");

      setOverlay(
        true,
        "Generating PEP",
        "Building the final DOCX document...",
        70
      );

      if (generatePepBtn) {
        generatePepBtn.disabled = true;
      }

      const response = await fetch(
        generateUrl,
        {
          method: "POST",
          body: formData,
          headers: {
            "X-CSRFToken": csrf,
          },
          credentials: "same-origin",
        }
      );

      if (!response.ok) {
        const contentType = (
          response.headers.get("content-type")
          || ""
        ).toLowerCase();

        if (
          contentType.includes(
            "application/json"
          )
        ) {
          const data = await response
            .json()
            .catch(() => null);

          throw new Error(
            data?.message
            || "No se pudo generar el PEP."
          );
        }

        throw new Error(
          "No se pudo generar el PEP."
        );
      }

      const blob = await response.blob();

      const filename =
        getDownloadFilename(response)
        || lastPreview.output_filename
        || "PEP.docx";

      triggerDownload(
        blob,
        filename
      );

      showOk(
        "PEP download started."
      );
    } catch (error) {
      showError(
        error?.message
        || "No se pudo generar el PEP."
      );
    } finally {
      setOverlay(false);

      if (generatePepBtn) {
        generatePepBtn.disabled = false;
      }
    }
  }


  function getDownloadFilename(response) {
    const headerFilename =
      response.headers.get("X-PEP-Filename");

    if (headerFilename) {
      return headerFilename;
    }

    const contentDisposition =
      response.headers.get(
        "Content-Disposition"
      ) || "";

    const match = contentDisposition.match(
      /filename="([^"]+)"/i
    );

    return match?.[1] || null;
  }


  function triggerDownload(
    blob,
    filename
  ) {
    const url =
      window.URL.createObjectURL(blob);

    const link =
      document.createElement("a");

    link.href = url;
    link.download = filename || "PEP.docx";

    document.body.appendChild(link);
    link.click();
    link.remove();

    window.URL.revokeObjectURL(url);
  }


  if (previewBtn) {
    previewBtn.addEventListener(
      "click",
      requestPreview
    );
  }

  if (papInfoBtn) {
    papInfoBtn.addEventListener(
      "click",
      openPapInfoModal
    );
  }

  if (pddInfoBtn) {
    pddInfoBtn.addEventListener(
      "click",
      openPddInfoModal
    );
  }

  if (generatePepBtn) {
    generatePepBtn.addEventListener(
      "click",
      generatePep
    );
  }

  if (viewJsonBtn) {
    viewJsonBtn.addEventListener(
      "click",
      openJsonModal
    );
  }

  if (viewRequirementsBtn) {
    viewRequirementsBtn.addEventListener(
      "click",
      openRequirementsModal
    );
  }

  if (papInput) {
    papInput.addEventListener(
      "change",
      resetPreview
    );
  }

  if (pddInput) {
    pddInput.addEventListener(
      "change",
      resetPreview
    );
  }

  resetPreview();
});