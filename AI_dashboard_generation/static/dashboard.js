const form = document.querySelector("#dashboard-form"),
  input = document.querySelector("#instruction"),
  button = document.querySelector("#generate"),
  statusEl = document.querySelector("#status"),
  grid = document.querySelector("#dashboard");
let charts = [];
const demoUser = document.querySelector("#demo-user");
demoUser.addEventListener("change", () => {
  charts.forEach((chart) => chart.destroy());
  charts = [];
  grid.replaceChildren();
  input.value = "";
  document.querySelector("#title").textContent = "";
  document.querySelector("#note").textContent = "";
  document.querySelector("#trace").hidden = true;
  document.querySelector("#trace pre").textContent = "";
  statusEl.textContent = "Profile changed. Generate a dashboard to load its saved preferences.";
});
document.querySelectorAll("[data-prompt]").forEach((node) =>
  node.addEventListener("click", () => {
    input.value = node.dataset.prompt;
    input.focus();
  }),
);
function render(widget) {
  const section = document.createElement("article");
  section.className = "widget";
  const title = document.createElement("h3");
  title.textContent = widget.title;
  section.append(title);
  if (widget.type === "card") {
    const value = document.createElement("div");
    value.className = "value";
    value.textContent = widget.value;
    section.append(value);
  } else if (widget.type === "bar" && typeof Chart !== "undefined") {
    const wrap = document.createElement("div");
    wrap.className = "chart-wrap";
    const canvas = document.createElement("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", widget.title);
    wrap.append(canvas);
    section.append(wrap);
    charts.push(
      new Chart(canvas, {
        type: "bar",
        data: {
          labels: widget.rows.map((row) => row[widget.group_by]),
          datasets: [
            {
              label: "Count",
              data: widget.rows.map((row) => row.count),
              backgroundColor: "#42785a",
              borderRadius: 5,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        },
      }),
    );
  } else {
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    const table = document.createElement("table"),
      head = document.createElement("thead"),
      header = document.createElement("tr");
    widget.columns.forEach((column) => {
      const th = document.createElement("th");
      th.textContent = column.replaceAll("_", " ");
      header.append(th);
    });
    head.append(header);
    table.append(head);
    const body = document.createElement("tbody");
    widget.rows.forEach((row) => {
      const tr = document.createElement("tr");
      widget.columns.forEach((column) => {
        const td = document.createElement("td");
        td.textContent = row[column] ?? "—";
        tr.append(td);
      });
      body.append(tr);
    });
    table.append(body);
    wrap.append(table);
    section.append(wrap);
    if (!widget.rows.length) {
      const p = document.createElement("p");
      p.textContent = "No matching records.";
      section.append(p);
    }
  }
  grid.append(section);
}
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (button.disabled) return;
  const userId = demoUser.value.trim();
  if (userId && !/^[A-Za-z0-9_-]{1,50}$/.test(userId)) {
    statusEl.textContent = "Use 1–50 letters, digits, underscores or hyphens for the demo user ID.";
    return;
  }
  button.disabled = true;
  demoUser.disabled = true;
  statusEl.className = "meta";
  statusEl.textContent =
    "Fetching complete datasets through MCP and generating your layout…";
  try {
    const response = await fetch("/dashboards/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instruction: input.value, user_id: userId || null }),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail),
      );
    charts.forEach((chart) => chart.destroy());
    charts = [];
    grid.replaceChildren();
    document.querySelector("#title").textContent = data.title;
    data.widgets.forEach(render);
    document.querySelector("#note").textContent = data.note;
    const trace = document.querySelector("#trace");
    trace.hidden = false;
    trace.querySelector("pre").textContent = JSON.stringify(
      { calls: data.trace, layout: data.spec },
      null,
      2,
    );
    statusEl.textContent = `Generated ${new Date(data.generated_at).toLocaleTimeString()} · ${data.dataset_counts.employees} employees · ${data.dataset_counts.items} items`;
  } catch (error) {
    statusEl.className = "meta error";
    statusEl.textContent = error.message;
    document.querySelector("#note").textContent =
      "Generation failed. Any dashboard still displayed is from the previous successful request.";
  } finally {
    button.disabled = false;
    demoUser.disabled = false;
  }
});
