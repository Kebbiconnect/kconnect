/* Announcement titles/messages are plain text, never executable HTML. */
document.addEventListener("DOMContentLoaded", function () {
    "use strict";
    const source = document.getElementById("kpn-announcement-data");
    const bar = document.getElementById("announcementBar");
    const content = document.getElementById("announcementContent");
    if (!source || !bar || !content) return;
    let announcements;
    try { announcements = JSON.parse(source.textContent); } catch (_) { return; }
    if (!Array.isArray(announcements) || announcements.length === 0) return;
    content.replaceChildren();
    announcements.forEach(function (announcement) {
        const item = document.createElement("div");
        item.className = "kpn-announcement-item";
        const title = document.createElement("strong");
        title.textContent = String(announcement.title || "") + ": ";
        const message = document.createElement("span");
        message.textContent = String(announcement.content || "");
        item.append(title, message);
        content.append(item);
    });
    bar.hidden = false;
});