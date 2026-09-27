const form = document.getElementById("status-form");
const message = document.getElementById("message");
const loginCard = document.getElementById("login-card");
const dashboard = document.getElementById("dashboard");

function showMessage(text, type) {
  message.textContent = text;
  message.className = `alert ${type}`;
  message.classList.remove("hidden");
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

function formatMoney(value) {
  if (value == null || value === "") return "—";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return String(value);
  return amount.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function personName(first, last) {
  return [first, last].filter(Boolean).join(" ") || "—";
}

function badgeKind(status) {
  const value = String(status || "").toUpperCase();
  if (value.includes("APPROV")) return "ok";
  if (value.includes("DENI") || value.includes("DENY")) return "danger";
  return "wait";
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

function renderSummary(data) {
  const grid = el("div", "dash-grid");
  const latest = data.priorAuthorizations[0];
  const insurance = data.insurance[0];
  const cards = [
    ["Prior authorization", latest ? latest.current_status : "None on file"],
    ["Insurance", insurance ? insurance.payer_name : "None on file"],
    ["Member ID", insurance ? insurance.member_id : "—"],
    ["Date of birth", formatDate(data.patient.dob)],
  ];
  for (const [label, value] of cards) {
    const card = el("article", "stat");
    card.append(el("span", null, label), el("strong", null, text(value)));
    grid.append(card);
  }
  return grid;
}

function renderAuthorizations(items) {
  const block = section("Prior authorization requests", "Status, requested service, and what you may still owe.");
  if (!items.length) {
    emptyNote(block, "No prior authorization requests are on file.");
    return block;
  }

  for (const item of items) {
    const card = el("article", "pa-card");
    const head = el("div", "pa-head");
    head.append(el("h3", null, text(item.service_description || item.request_type)));
    head.append(el("span", `badge ${badgeKind(item.current_status)}`, text(item.current_status)));
    card.append(head);

    const details = el("div", "details");
    details.append(
      row("Requested", formatDate(item.requested_date)),
      row("Requested start", formatDate(item.requested_start_date)),
      row("Urgency", text(item.urgency)),
      row("Units", text(item.units_requested)),
      row("Diagnosis", text(item.diagnosis_description)),
      row("Requesting doctor", `${personName(item.provider_first_name, item.provider_last_name)}${item.specialty ? ` · ${item.specialty}` : ""}`),
      row("Payer", text(item.payer_name)),
      row("Letter of medical necessity", item.letterOnFile ? `On file · ${formatDate(item.letterDate)}` : "Not on file")
    );
    card.append(details);

    if (item.cost) {
      const cost = el("div", "details");
      cost.append(el("h3", null, "Your cost"));
      cost.append(
        row("Deductible", formatMoney(item.cost.deductible_amount)),
        row("Copay", formatMoney(item.cost.copay_amount)),
        row("Coinsurance", item.cost.coinsurance_pct == null ? "—" : `${item.cost.coinsurance_pct}%`),
        row("Estimated responsibility", formatMoney(item.cost.total_patient_responsibility))
      );
      card.append(cost);
    }

    if (item.history.length) {
      const list = el("ol", "timeline");
      for (const event of item.history) {
        const entry = el("li");
        entry.append(el("strong", null, text(event.status)), el("span", null, ` ${formatDate(event.status_date)}`));
        if (event.notes) entry.append(el("p", "meta", event.notes));
        list.append(entry);
      }
      card.append(el("h3", null, "Status history"), list);
    }

    if (item.appeals.length) {
      const list = el("div", "details");
      list.append(el("h3", null, "Appeal"));
      for (const appeal of item.appeals) {
        list.append(
          row("Status", text(appeal.appeal_status)),
          row("Filed", formatDate(appeal.appeal_date)),
          row("Decision", formatDate(appeal.decision_date)),
          row("Additional information", text(appeal.additional_info))
        );
      }
      card.append(list);
    }

    if (item.documents.length) {
      const list = el("ul", "files");
      for (const doc of item.documents) {
        list.append(el("li", null, `${text(doc.type_name)} · ${formatDate(doc.uploaded_date)}`));
      }
      card.append(el("h3", null, "Documents on file"), list);
    }

    block.append(card);
  }
  return block;
}

function renderInsurance(items) {
  const block = section("Insurance");
  if (!items.length) {
    emptyNote(block, "No insurance is on file.");
    return block;
  }
  for (const item of items) {
    const details = el("div", "details");
    details.append(
      row("Plan", text(item.payer_name)),
      row("Member ID", text(item.member_id)),
      row("Group", text(item.group_number)),
      row("Effective", formatDate(item.effective_date)),
      row("Ends", formatDate(item.termination_date)),
      row("Prior auth phone", text(item.pa_dept_phone)),
      row("Prior auth fax", text(item.pa_dept_fax))
    );
    block.append(details);
  }
  return block;
}

function renderSimpleList(title, items, renderItem) {
  if (!items.length) return null;
  const block = section(title);
  const list = el("ul", "plain-list");
  for (const item of items) list.append(renderItem(item));
  block.append(list);
  return block;
}

function renderDashboard(data) {
  dashboard.replaceChildren();
  const head = el("div", "dash-head card");
  const titles = el("div");
  titles.append(
    el("h1", null, personName(data.patient.firstName, data.patient.lastName)),
    el(
      "p",
      "meta",
      `Patient ID ${data.patient.patientId} · ${text(data.patient.sex)} · ${text(data.patient.phone)}`
    ),
    el("p", "meta", text(data.patient.address))
  );
  const logout = el("button", "btn patient", "Log out");
  logout.type = "button";
  logout.addEventListener("click", () => {
    dashboard.classList.add("hidden");
    dashboard.replaceChildren();
    loginCard.classList.remove("hidden");
    form.reset();
    message.classList.add("hidden");
  });
  head.append(titles, logout);
  dashboard.append(head, renderSummary(data), renderAuthorizations(data.priorAuthorizations), renderInsurance(data.insurance));

  const diagnoses = renderSimpleList("Diagnoses", data.diagnoses, (item) => {
    const line = el("li");
    line.append(
      el("strong", null, text(item.icd10_description || item.icd10_code)),
      el(
        "span",
        null,
        ` · ${text(item.diagnosis_type)} · ${formatDate(item.diagnosis_date)} · ${personName(item.provider_first_name, item.provider_last_name)}`
      )
    );
    if (item.clinical_notes) line.append(el("p", "meta", item.clinical_notes));
    return line;
  });
  const allergies = renderSimpleList("Allergies", data.allergies, (item) =>
    el("li", null, `${text(item.allergen)} · ${text(item.reaction)}`)
  );
  const medications = renderSimpleList("Medications", data.medications, (item) => {
    const line = el("li");
    line.textContent = `${text(item.drug_name)} · ${text(item.dosage)} · ${text(item.frequency)} · ${text(item.status)} · started ${formatDate(item.start_date)}`;
    return line;
  });
  const labs = renderSimpleList("Lab results", data.labs, (item) =>
    el(
      "li",
      null,
      `${text(item.test_name)} · ${text(item.result_value)} ${item.unit || ""} · ${text(item.flag)} · ${formatDate(item.collected_date)}`
    )
  );
  const imaging = renderSimpleList("Imaging", data.imaging, (item) => {
    const line = el("li");
    line.append(el("strong", null, `${text(item.exam_type)} · ${formatDate(item.exam_date)}`));
    if (item.impression) line.append(el("p", "meta", item.impression));
    return line;
  });
  const treatments = renderSimpleList("Previous treatments", data.treatments, (item) =>
    el(
      "li",
      null,
      `${text(item.treatment_type)} · ${text(item.description)} · ${formatDate(item.start_date)} to ${formatDate(item.end_date)} · ${text(item.outcome)}`
    )
  );

  for (const block of [diagnoses, allergies, medications, labs, imaging, treatments]) {
    if (block) dashboard.append(block);
  }

  const socialHistory = data.socialHistory || [];
  if (data.surgeries.length || data.familyHistory.length || socialHistory.length) {
    const history = section("Health history");
    const details = el("div", "details");
    socialHistory.forEach((item, index) => {
      const label = socialHistory.length > 1 ? `Social history ${index + 1}` : "Social history";
      details.append(
        row(label, `${text(item.smoking_status)} · ${text(item.alcohol_use)} · ${text(item.occupation)}`)
      );
    });
    for (const surgery of data.surgeries) {
      details.append(row("Surgery", `${text(surgery.procedure_name)} · ${formatDate(surgery.procedure_date)}`));
    }
    for (const relative of data.familyHistory) {
      details.append(row(text(relative.relation), text(relative.condition_desc)));
    }
    history.append(details);
    dashboard.append(history);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  dashboard.classList.add("hidden");

  try {
    const response = await fetch("/api/patient/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        patientName: form.patientName.value,
        patientId: form.patientId.value,
      }),
    });
    const data = await response.json();
    if (response.status === 401) {
      showMessage(data.error || "Not authorized.", "error");
      return;
    }
    if (!response.ok || !data.ok) {
      showMessage(data.error || "Sign-in failed.", "error");
      return;
    }

    message.classList.add("hidden");
    loginCard.classList.add("hidden");
    renderDashboard(data.record);
    dashboard.classList.remove("hidden");
  } catch {
    showMessage("Could not reach the server.", "error");
  }
});
