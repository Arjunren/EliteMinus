/* ---------------------------------------------------------------------------
 * auth.js — controllers for login.html, register.html, verify.html and
 * forgot.html. Each page includes this file; it wires up whichever form it
 * finds. Sign-up is two steps: register (code e-mailed) then verify.
 * ------------------------------------------------------------------------- */
const PENDING_EMAIL = "em_pending_email";

function banner(message, kind = "error") {
  const box = document.getElementById("banner");
  if (!box) return;
  const styles = {
    error: "bg-red-500/15 text-red-300 border-red-500/30",
    success: "bg-brand/15 text-brand border-brand/30",
    info: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  };
  box.className = "mb-4 rounded-md px-4 py-3 text-sm border " + styles[kind];
  box.textContent = message;
  box.classList.remove("hidden");
}

function clearBanner() {
  const box = document.getElementById("banner");
  if (box) box.classList.add("hidden");
}

function busy(form, on, label) {
  const button = form.querySelector('button[type="submit"]');
  if (!button) return;
  if (on) {
    button.dataset.label = button.textContent;
    button.disabled = true;
    button.textContent = label || "Please wait…";
    button.classList.add("opacity-60");
  } else {
    button.disabled = false;
    button.textContent = button.dataset.label || button.textContent;
    button.classList.remove("opacity-60");
  }
}

/* ===================== LOGIN ===================== */
function initLogin() {
  const form = document.getElementById("login-form");
  if (!form) return;

  if (Auth.token) { location.replace("index.html"); return; }
  if (new URLSearchParams(location.search).has("expired"))
    banner("Your session expired. Please log in again.", "info");
  if (new URLSearchParams(location.search).has("registered"))
    banner("Your account is ready — log in to start listening.", "success");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearBanner();
    busy(form, true, "Signing in…");
    const fd = new FormData(form);
    try {
      const res = await API.login({
        identifier: (fd.get("identifier") || "").trim(),
        password: fd.get("password"),
      });
      Auth.save(res.token, res.user);
      location.replace("index.html");
    } catch (err) {
      busy(form, false);
      // An unverified account gets bounced straight to the code screen.
      if (err.data && err.data.code === "unverified") {
        localStorage.setItem(PENDING_EMAIL, err.data.email);
        location.href = "verify.html?resent=" + (err.data.otp_sent ? "1" : "0");
        return;
      }
      if (err.data && err.data.developer) {
        banner(err.message + " — " + err.data.developer.email);
        return;
      }
      banner(err.message);
    }
  });
}

/* ===================== REGISTER ===================== */
function initRegister() {
  const form = document.getElementById("register-form");
  if (!form) return;
  if (Auth.token) { location.replace("index.html"); return; }

  const password = form.querySelector('[name="password"]');
  const confirm = form.querySelector('[name="confirm"]');
  const meter = document.getElementById("pw-meter");

  password.addEventListener("input", () => {
    if (!meter) return;
    const value = password.value;
    let score = 0;
    if (value.length >= 8) score++;
    if (/[a-zA-Z]/.test(value) && /[0-9]/.test(value)) score++;
    if (value.length >= 12) score++;
    if (/[^a-zA-Z0-9]/.test(value)) score++;
    const labels = ["Too short", "Weak", "Okay", "Good", "Strong"];
    const colors = ["bg-red-500", "bg-red-500", "bg-amber-500", "bg-sky-500", "bg-emerald-500"];
    meter.innerHTML = `
      <div class="flex gap-1 mb-1">
        ${[0, 1, 2, 3].map((i) => `<div class="h-1 flex-1 rounded ${i < score ? colors[score] : "bg-neutral-700"}"></div>`).join("")}
      </div>
      <p class="text-xs text-neutral-500">${value ? labels[score] : "At least 8 characters, mixing letters and numbers"}</p>`;
  });

  confirm.addEventListener("input", () => {
    confirm.setCustomValidity(
      confirm.value && confirm.value !== password.value ? "Passwords do not match" : "");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearBanner();
    const fd = new FormData(form);
    const email = (fd.get("email") || "").trim().toLowerCase();

    busy(form, true, "Sending code…");
    try {
      await API.register({
        username: (fd.get("username") || "").trim(),
        email,
        password: fd.get("password"),
        confirm: fd.get("confirm"),
      });
      localStorage.setItem(PENDING_EMAIL, email);
      location.href = "verify.html";
    } catch (err) {
      busy(form, false);
      const all = (err.data && err.data.errors) || [err.message];
      banner(all.join(" "));
    }
  });
}

/* ===================== VERIFY (OTP) ===================== */
function initVerify() {
  const form = document.getElementById("verify-form");
  if (!form) return;

  const email = localStorage.getItem(PENDING_EMAIL) || "";
  const target = document.getElementById("verify-email");
  if (!email) { location.replace("register.html"); return; }
  if (target) target.textContent = email;

  if (new URLSearchParams(location.search).get("resent") === "1")
    banner("Your e-mail isn't verified yet — we've sent a fresh code.", "info");

  const code = form.querySelector('[name="code"]');
  code.focus();
  // Strip anything that isn't a digit, and submit as soon as it's full.
  code.addEventListener("input", () => {
    code.value = code.value.replace(/\D/g, "");
    if (code.value.length === code.maxLength) form.requestSubmit();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearBanner();
    busy(form, true, "Verifying…");
    try {
      const res = await API.verifyOtp({ email, code: code.value });
      localStorage.removeItem(PENDING_EMAIL);
      if (res.status === "awaiting_approval") {
        banner(res.message, "success");
        busy(form, false);
        setTimeout(() => location.replace("login.html"), 3500);
        return;
      }
      Auth.save(res.token, res.user);
      location.replace("index.html");
    } catch (err) {
      busy(form, false);
      code.value = "";
      code.focus();
      banner(err.message);
    }
  });

  // Resend, with a visible cooldown so people don't hammer it.
  const resend = document.getElementById("resend-btn");
  let cooldown = 0;
  const tick = () => {
    if (cooldown <= 0) {
      resend.disabled = false;
      resend.textContent = "Didn't get it? Send a new code";
      return;
    }
    resend.disabled = true;
    resend.textContent = `Send a new code in ${cooldown}s`;
    cooldown--;
    setTimeout(tick, 1000);
  };

  resend.addEventListener("click", async () => {
    clearBanner();
    resend.disabled = true;
    try {
      const res = await API.resendOtp(email);
      banner(res.message || "A new code is on its way.", "success");
      cooldown = 60;
    } catch (err) {
      banner(err.message);
      cooldown = (err.data && err.data.retry_after) || 30;
    }
    tick();
  });
}

/* ===================== FORGOT PASSWORD ===================== */
async function initForgot() {
  const form = document.getElementById("forgot-form");
  if (!form) return;

  // Show the developer's real contact details rather than hard-coding them.
  try {
    const dev = await API.developer();
    const box = document.getElementById("dev-contact");
    if (box) {
      box.innerHTML = `
        <p class="font-semibold text-white mb-1">${escapeHtml(dev.name || "The developer")}</p>
        ${dev.email ? `<p><a href="mailto:${escapeHtml(dev.email)}?subject=EliteMinus%20password%20reset"
             class="text-brand hover:underline break-all">${escapeHtml(dev.email)}</a></p>` : ""}
        ${dev.phone ? `<p class="text-neutral-300">${escapeHtml(dev.phone)}</p>` : ""}`;
    }
  } catch (e) { /* the static contact copy on the page still stands */ }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearBanner();
    busy(form, true, "Sending…");
    const fd = new FormData(form);
    try {
      const res = await API.passwordHelp({
        email: (fd.get("email") || "").trim().toLowerCase(),
        message: fd.get("message") || "",
      });
      form.classList.add("hidden");
      banner(res.message, "success");
    } catch (err) {
      busy(form, false);
      banner(err.message);
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initLogin();
  initRegister();
  initVerify();
  initForgot();
});
