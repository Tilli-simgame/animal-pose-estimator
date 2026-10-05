"use strict";

let me = null;

init();

async function init() {
  me = await initUserBar();
  document.getElementById("new-user").addEventListener("submit", createUser);
  await loadUsers();
}

// Temporary password: 14 characters without look-alikes (0/O, 1/l/I)
function tempPassword() {
  const chars = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(14));
  return Array.from(bytes, (b) => chars[b % chars.length]).join("");
}

function showMessage(id, html, error = false) {
  const el = document.getElementById(id);
  el.innerHTML = html;
  el.classList.toggle("error", error);
}

async function createUser(e) {
  e.preventDefault();
  const form = e.target;
  const password = tempPassword();
  try {
    const { user } = await apiJson("/api/users", "POST", {
      username: form.username.value,
      display_name: form.display_name.value,
      role: form.role.value,
      password,
    });
    form.reset();
    showMessage("new-user-msg",
      `Käyttäjä <strong>${escapeHtml(user.username)}</strong> luotu. Väliaikainen salasana: <code class="secret">${password}</code>`);
    await loadUsers();
  } catch (err) {
    showMessage("new-user-msg", escapeHtml(err.message), true);
  }
}

async function loadUsers() {
  const { users } = await apiJson("/api/users");
  const rows = document.getElementById("user-rows");
  rows.replaceChildren();
  for (const u of users) {
    const self = u.id === me.id;
    const tr = document.createElement("tr");
    tr.classList.toggle("inactive", !u.active);
    tr.innerHTML = `
      <td>${escapeHtml(u.username)}${self ? " (sinä)" : ""}</td>
      <td>${escapeHtml(u.display_name)}</td>
      <td>
        <select data-action="role" ${self ? "disabled" : ""}>
          <option value="judge" ${u.role === "judge" ? "selected" : ""}>Tuomari</option>
          <option value="admin" ${u.role === "admin" ? "selected" : ""}>Ylläpitäjä</option>
        </select>
      </td>
      <td>
        ${u.active ? "Aktiivinen" : "Suljettu"}
        ${self ? "" : `<button class="secondary small" data-action="active">${u.active ? "Sulje" : "Aktivoi"}</button>`}
      </td>
      <td><button class="secondary small" data-action="password">Uusi salasana</button></td>`;

    tr.querySelector('[data-action="role"]').addEventListener("change", (e) =>
      change(u, { role: e.target.value }, `Rooli vaihdettu: ${u.username}`));
    tr.querySelector('[data-action="active"]')?.addEventListener("click", () =>
      change(u, { active: !u.active }, `${u.active ? "Tunnus suljettu" : "Tunnus aktivoitu"}: ${u.username}`));
    tr.querySelector('[data-action="password"]').addEventListener("click", () => {
      const password = tempPassword();
      change(u, { password },
        `Uusi väliaikainen salasana käyttäjälle ${escapeHtml(u.username)}: <code class="secret">${password}</code>`, true);
    });
    rows.appendChild(tr);
  }
}

async function change(user, body, message, messageIsHtml = false) {
  try {
    await apiJson(`/api/users/${user.id}`, "PATCH", body);
    showMessage("table-msg", messageIsHtml ? message : escapeHtml(message));
  } catch (err) {
    showMessage("table-msg", escapeHtml(err.message), true);
  }
  await loadUsers();
}
