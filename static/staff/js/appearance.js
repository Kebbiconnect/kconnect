/* KPN appearance: same System / Light / Dark choices as the native client. */
(function () {
    "use strict";
    const key = "kpnAppearance";
    const choices = ["system", "light", "dark"];
    let choice = "system";
    try {
        const stored = localStorage.getItem(key);
        if (choices.includes(stored)) {
            choice = stored;
        } else if (stored === null && localStorage.getItem("darkMode") !== null) {
            choice = localStorage.getItem("darkMode") === "true" ? "dark" : "light";
        }
    } catch (_) { /* Browsing with storage disabled must still work. */ }
    const system = window.matchMedia("(prefers-color-scheme: dark)");
    function apply() {
        const dark = choice === "dark" || (choice === "system" && system.matches);
        document.documentElement.classList.toggle("dark", dark);
        document.documentElement.style.colorScheme = dark ? "dark" : "light";
        document.querySelectorAll("[data-appearance-select]").forEach(function (select) {
            select.value = choice;
        });
    }
    function select(value) {
        choice = choices.includes(value) ? value : "system";
        try { localStorage.setItem(key, choice); } catch (_) {}
        apply();
    }
    if (system.addEventListener) system.addEventListener("change", apply);
    else if (system.addListener) system.addListener(apply);
    apply(); // Before styles paint; avoids a light flash in dark mode.
    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-appearance-select]").forEach(function (control) {
            control.addEventListener("change", function () { select(control.value); });
        });
        apply();
    });
})();