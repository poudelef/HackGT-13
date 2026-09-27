const loginCard = document.getElementById("login-card");
const loginForm = document.getElementById("login-form");
const loginMessage = document.getElementById("login-message");
const workspace = document.getElementById("workspace");
const lookupForm = document.getElementById("lookup-form");
const lookupMessage = document.getElementById("lookup-message");
const chart = document.getElementById("chart");
const applyCard = document.getElementById("apply-card");
const authForm = document.getElementById("auth-form");
const saveMessage = document.getElementById("save-message");
const saveButton = document.getElementById("save-button");

let session = null;

function showMessage(node, text, type) {
  node.textContent = text;
  node.className = `alert ${type}`;
  node.classList.remove("hidden");
}

function hideMessage(node) {
  node.classList.add("hidden");
}

function text(value) {
  const cleaned = value == null ? "" : String(value).trim();
  return cleaned || "—";
}

function formatDate(value) {
  if (!value) return "—";
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return String(value);
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function personName(first, last) {
  return [first, last].filter(Boolean).join(" ") || "—";
}

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content != null) node.textContent = content;
  return node;
}

function row(label, value) {
  const line = el("div", "row");
  line.append(el("span", null, label), el("span", null, value));
  return line;
}

function section(title, hint) {
  const block = el("section", "card dash-section");
  block.append(el("h2", null, title));
  if (hint) block.append(el("p", "meta", hint));
  return block;
}

function emptyNote(parent, copy) {
  parent.append(el("p", "meta", copy));
}

function resetChart() {
  chart.classList.add("hidden");
  chart.replaceChildren();
  applyCard.classList.add("hidden");
  authForm.reset();
  saveButton.disabled = false;
  hideMessage(saveMessage);
}

function renderList(title, items, renderItem, emptyCopy) {
  const block = section(title);
  if (!items.length) {
    emptyNote(block, emptyCopy);
    return block;
  }
  const list = el("ul", "plain-list");
  for (const item of items) list.append(renderItem(item));
  block.append(list);
  return block;
}

function renderChart(data) {
  chart.replaceChildren();
  const patient = data.patient;
  const general = section("General information");
  const details = el("div", "details");
  details.append(
    row("Name", personName(patient.firstName, patient.lastName)),
    row("Patient ID", String(patient.patientId)),
    row("Date of birth", formatDate(patient.dob)),
    row("Sex", text(patient.sex)),
    row("Phone", text(patient.phone)),
    row("Address", text(patient.address))
  );
  general.append(details);
  chart.append(general);

  chart.append(
    renderList(
      "Allergies",
      data.allergies,
      (item) => el("li", null, `${text(item.allergen)} · ${text(item.reaction)}`),
      "No allergies are on file."
    )
  );

  chart.append(
    renderList(
      "Previous treatments",
      data.treatments,
      (item) =>
        el(
          "li",
          null,
          `${text(item.treatment_type)} · ${text(item.description)} · ${formatDate(item.start_date)} to ${formatDate(item.end_date)} · ${text(item.outcome)}`
        ),
      "No previous treatments are on file."
    )
  );

  chart.classList.remove("hidden");
}

async function lookupPatient() {
  const response = await fetch("/api/doctor/patient", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      providerId: session.providerId,
      npi: session.npi,
      patientName: lookupForm.patientName.value,
      patientId: lookupForm.patientId.value,
    }),
  });
  const data = await response.json();
  return { response, data };
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideMessage(loginMessage);
  try {
    const response = await fetch("/api/doctor/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        providerId: loginForm.providerId.value,
        npi: loginForm.npi.value,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      showMessage(loginMessage, data.error || "Not authorized.", "error");
      return;
    }
    session = {
      providerId: data.provider.providerId,
      npi: data.provider.npi,
    };
    document.getElementById("doctor-label").textContent =
      `Signed in as Dr. ${data.provider.firstName} ${data.provider.lastName} · ${data.provider.specialty || "Provider"}`;
    document.getElementById("doctor-clinic").textContent = data.provider.clinicName || "";
    loginCard.classList.add("hidden");
    workspace.classList.remove("hidden");
    resetChart();
    hideMessage(lookupMessage);
  } catch {
    showMessage(loginMessage, "Could not reach the server.", "error");
  }
});

document.getElementById("logout").addEventListener("click", () => {
  session = null;
  workspace.classList.add("hidden");
  loginCard.classList.remove("hidden");
  loginForm.reset();
  lookupForm.reset();
  resetChart();
  hideMessage(loginMessage);
  hideMessage(lookupMessage);
});

lookupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!session) return;
  hideMessage(lookupMessage);
  resetChart();
  try {
    const { response, data } = await lookupPatient();
    if (response.status === 404) {
      showMessage(lookupMessage, data.error || "Patient not found.", "error");
      return;
    }
    if (!response.ok || !data.ok) {
      showMessage(lookupMessage, data.error || "Lookup failed.", "error");
      return;
    }

    renderChart(data.record);
    applyCard.classList.remove("hidden");
    if (!data.record.insurance.length) {
      saveButton.disabled = true;
      showMessage(lookupMessage, "Patient found, but no insurance is on file, so a prior authorization cannot be filed.", "error");
    }
  } catch {
    showMessage(lookupMessage, "Could not reach the server.", "error");
  }
});

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!session) return;
  const files = authForm.pdfs.files;
  if (!files.length) {
    showMessage(saveMessage, "Choose at least one PDF.", "error");
    return;
  }
  if (files.length > 10) {
    showMessage(saveMessage, "You can upload at most 10 PDF files.", "error");
    return;
  }
  for (const file of files) {
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      showMessage(saveMessage, "Only PDF files are allowed.", "error");
      return;
    }
  }

  const body = new FormData(authForm);
  body.set("providerId", session.providerId);
  body.set("npi", session.npi);
  body.set("patientName", lookupForm.patientName.value);
  body.set("patientId", lookupForm.patientId.value);
  showMessage(saveMessage, "Reading the PDFs and filing the request...", "ok");
  saveButton.disabled = true;

  try {
    const response = await fetch("/api/doctor/authorization", { method: "POST", body });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      showMessage(saveMessage, data.error || "Could not file the authorization.", "error");
      return;
    }
    const failed = (data.files || []).filter((file) => file.extractionError);
    showMessage(
      saveMessage,
      failed.length
        ? `Prior authorization ${data.paId} filed. ${failed.length} PDF(s) could not be read.`
        : `Prior authorization ${data.paId} filed.`,
      failed.length ? "error" : "ok"
    );
    authForm.reset();
    const refreshed = await lookupPatient();
    if (refreshed.response.ok && refreshed.data.ok) renderChart(refreshed.data.record);
  } catch {
    showMessage(saveMessage, "Could not reach the server.", "error");
  } finally {
    saveButton.disabled = false;
  }
});
