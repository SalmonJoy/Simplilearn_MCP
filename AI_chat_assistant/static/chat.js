const form = document.querySelector("#chat-form"),
  input = document.querySelector("#message"),
  messages = document.querySelector("#messages"),
  statusEl = document.querySelector("#status"),
  send = document.querySelector("#send");
let history = [];
function append(role, text) {
  const node = document.createElement("article");
  node.className = `message ${role}`;
  node.textContent = text;
  messages.append(node);
  messages.scrollTop = messages.scrollHeight;
}
function trace(rows) {
  if (!rows.length) return;
  const details = document.createElement("details"),
    summary = document.createElement("summary"),
    pre = document.createElement("pre");
  summary.textContent = `MCP trace · ${rows.length} tool call${rows.length === 1 ? "" : "s"}`;
  pre.textContent = JSON.stringify(rows, null, 2);
  details.append(summary, pre);
  messages.append(details);
}
document.querySelectorAll("[data-prompt]").forEach((button) =>
  button.addEventListener("click", () => {
    input.value = button.dataset.prompt;
    input.focus();
  }),
);
document.querySelector("#clear").addEventListener("click", () => {
  if (send.disabled) return;
  history = [];
  messages.replaceChildren();
  append("assistant", "Conversation cleared. What would you like to explore?");
});
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message || send.disabled) return;
  append("user", message);
  input.value = "";
  send.disabled = true;
  statusEl.className = "";
  statusEl.textContent = "Discovering tools and working on your request…";
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history: history.slice(-40) }),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail),
      );
    append("assistant", data.answer);
    trace(data.trace);
    history.push(
      { role: "user", content: message },
      { role: "assistant", content: data.answer.slice(0, 20000) },
    );
    statusEl.textContent = "Ready · open the trace to inspect MCP calls.";
  } catch (error) {
    append("assistant", `Request failed: ${error.message}`);
    statusEl.className = "error";
    statusEl.textContent =
      "Check the services and try again. Review records before repeating a write.";
  } finally {
    send.disabled = false;
    input.focus();
  }
});
