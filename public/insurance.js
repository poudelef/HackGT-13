const form = document.getElementById("login-form");
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

function formatMonth(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})/);
  if (!match) return text(value);
  const date = new Date(Number(match[1]), Number(match[2]) - 1, 1);
  return date.toLocaleDateString(undefined, { year: "numeric", month: "long" });
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

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content != null) node.textContent = content;
  return node;
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

function moneySum(rows, field) {
  return rows.reduce((total, row) => total + (Number(row[field]) || 0), 0);
}

function countStatus(rows, status) {
  return rows.filter((row) => String(row.current_status) === status).length;
}

function todayKey() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function isActive(member) {
  if (!member.termination_date) return true;
  return String(member.termination_date).slice(0, 10) >= todayKey();
}

function table(headers, rows) {
  const wrap = el("div", "table-wrap");
  const grid = el("table", "data-table");
  const head = el("thead");
  const headRow = el("tr");
  for (const header of headers) headRow.append(el("th", null, header));
  head.append(headRow);
  const body = el("tbody");
  for (const cells of rows) {
    const line = el("tr");
    for (const cell of cells) line.append(el("td", null, cell));
    body.append(line);
  }
  grid.append(head, body);
  wrap.append(grid);
  return wrap;
}

function renderDashboard(data) {
  dashboard.replaceChildren();
  const payer = data.payer;
  const members = data.members || [];
  const requests = data.requests || [];
  const monthly = data.monthly || [];
  const appeals = data.appeals || [];
  const activeMembers = members.filter(isActive).length;
  const openRequests = requests.filter((row) => ["SUBMITTED", "UNDER_REVIEW"].includes(row.current_status)).length;

  const head = el("div", "dash-head card");
  const titles = el("div");
  titles.append(
    el("h1", null, text(payer.name)),
    el("p", "meta", `Payer ID ${payer.payer_id} · ${text(payer.payer_code)}`),
    el("p", "meta", `Prior auth ${text(payer.pa_dept_phone)} · fax ${text(payer.pa_dept_fax)}`)
  );
  const logout = el("button", "btn insurance", "Log out");
  logout.type = "button";
  logout.addEventListener("click", () => {
    dashboard.classList.add("hidden");
    dashboard.replaceChildren();
    loginCard.classList.remove("hidden");
    form.reset();
    message.classList.add("hidden");
  });
  head.append(titles, logout);

  const grid = el("div", "dash-grid");
  const cards = [
    ["Members", String(members.length)],
    ["Active coverage", String(activeMembers)],
    ["Open requests", String(openRequests)],
    ["Patient responsibility", formatMoney(moneySum(requests, "total_patient_responsibility"))],
  ];
  for (const [label, value] of cards) {
    const card = el("article", "stat");
    card.append(el("span", null, label), el("strong", null, value));
    grid.append(card);
  }

  const volume = section("Authorization volume", "Counts for this payer only. Status comes from the request, not a clinical chart.");
  volume.append(
    table(
      ["Submitted", "Under review", "Approved", "Denied", "Appeals"],
      [[
        String(countStatus(requests, "SUBMITTED")),
        String(countStatus(requests, "UNDER_REVIEW")),
        String(countStatus(requests, "APPROVED")),
        String(countStatus(requests, "DENIED")),
        String(appeals.length),
      ]]
    )
  );

  const months = section(
    "Monthly patient responsibility",
    "Grouped by the month the authorization was requested. Amounts are copay, deductible, and estimated patient responsibility on file."
  );
  if (!monthly.length) {
    emptyNote(months, "No authorization requests are on file for a month yet.");
  } else {
    months.append(
      table(
        ["Month", "Patients", "Requests", "Copay", "Deductible", "Patient responsibility"],
        monthly.map((row) => [
          formatMonth(row.month_key),
          String(row.patients),
          String(row.requests),
          formatMoney(row.copay),
          formatMoney(row.deductible),
          formatMoney(row.responsibility),
        ])
      )
    );
  }

  const roster = section("Members", "People covered by this payer, with their member ID and group.");
  if (!members.length) {
    emptyNote(roster, "No members are on file.");
  } else {
    roster.append(
      table(
        ["Member", "Member ID", "Group", "Effective", "Ends", "Requests", "Open"],
        members.map((row) => [
          personName(row.first_name, row.last_name),
          text(row.member_id),
          text(row.group_number),
          formatDate(row.effective_date),
          formatDate(row.termination_date),
          String(row.request_count || 0),
          String(row.open_requests || 0),
        ])
      )
    );
  }

  const queue = section("Prior authorization requests", "Service, status, and what the member may owe. Clinical history is not shown.");
  if (!requests.length) {
    emptyNote(queue, "No prior authorization requests are on file.");
  } else {
    queue.append(
      table(
        ["Member", "Service", "Status", "Urgency", "Requested", "Copay", "Deductible", "Coinsurance", "Responsibility"],
        requests.map((row) => [
          `${personName(row.first_name, row.last_name)} · ${text(row.member_id)}`,
          text(row.service_description || row.request_type),
          text(row.current_status),
          text(row.urgency),
          formatDate(row.requested_date),
          formatMoney(row.copay_amount),
          formatMoney(row.deductible_amount),
          row.coinsurance_pct == null ? "—" : `${row.coinsurance_pct}%`,
          formatMoney(row.total_patient_responsibility),
        ])
      )
    );
  }

  const appealBlock = section("Appeals");
  if (!appeals.length) {
    emptyNote(appealBlock, "No appeals are on file.");
  } else {
    appealBlock.append(
      table(
        ["Member", "Service", "Status", "Filed", "Decision"],
        appeals.map((row) => [
          `${personName(row.first_name, row.last_name)} · ${text(row.member_id)}`,
          text(row.service_description),
          text(row.appeal_status),
          formatDate(row.appeal_date),
          formatDate(row.decision_date),
        ])
      )
    );
  }

  dashboard.append(head, grid, volume, months, roster, queue, appealBlock);
  dashboard.classList.remove("hidden");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  dashboard.classList.add("hidden");
  try {
    const response = await fetch("/api/insurance/dashboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payerId: form.payerId.value }),
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
  } catch {
    showMessage("Could not reach the server.", "error");
  }
});
