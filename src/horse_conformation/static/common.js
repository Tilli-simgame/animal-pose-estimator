"use strict";

// Shared by the signed-in pages: API helper and the user bar in the header.

async function api(url, options = {}) {
  const res = await fetch(url, options);
  if (res.status === 401 && !url.startsWith("/api/login")) {
    location.href = "/login";
    throw new Error("Kirjaudu sisään.");
  }
  return res;
}

async function apiJson(url, method = "GET", body = undefined) {
  const res = await api(url, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorText(data));
  return data;
}

function errorText(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return "Tarkista lomakkeen arvot.";
  return "Jokin meni pieleen.";
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

async function initUserBar() {
  const { user } = await apiJson("/api/me");
  const bar = document.getElementById("user-bar");
  bar.innerHTML = `
    <span class="who">${escapeHtml(user.display_name)}${user.role === "admin" ? " · ylläpitäjä" : ""}</span>
    ${location.pathname !== "/" ? '<a href="/">Analyysi</a>' : ""}
    ${user.role === "admin" && location.pathname !== "/users" ? '<a href="/users">Käyttäjät</a>' : ""}
    <details class="menu">
      <summary>Vaihda salasana</summary>
      <form id="password-form" class="popover">
        <label>Nykyinen salasana <input name="current" type="password" autocomplete="current-password" required></label>
        <label>Uusi salasana (väh. 10 merkkiä) <input name="new" type="password" autocomplete="new-password" minlength="10" required></label>
        <button type="submit">Vaihda</button>
        <p class="form-msg" role="status"></p>
      </form>
    </details>
    <button id="logout" class="secondary">Kirjaudu ulos</button>`;

  document.getElementById("logout").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    location.href = "/login";
  });
  const form = document.getElementById("password-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = form.querySelector(".form-msg");
    try {
      await apiJson("/api/me/password", "POST", { current: form.current.value, new: form.new.value });
      form.reset();
      msg.textContent = "Salasana vaihdettu. Muut laitteet kirjattiin ulos.";
      msg.classList.remove("error");
    } catch (err) {
      msg.textContent = err.message;
      msg.classList.add("error");
    }
  });
  return user;
}
