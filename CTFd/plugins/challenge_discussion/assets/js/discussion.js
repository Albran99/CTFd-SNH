/**
 * challenge_discussion/assets/js/discussion.js
 *
 * Injects three buttons into the challenge modal footer:
 *   - "General"  → /challenges/{id}/discuss/general  (open to all)
 *   - "Spoiler"  → /challenges/{id}/discuss/spoiler  (solve-gated)
 *   - "Writeup"  → /challenges/{id}/discuss/writeup  (solve-gated, with rubric grading)
 */
(function () {
    "use strict";

    function getChallengeId() {
        try {
            if (window.Alpine) {
                var data = Alpine.store("challenge") && Alpine.store("challenge").data;
                if (data && data.id) return data.id;
            }
        } catch (e) {}
        var input = document.querySelector("#challenge-window #challenge-id");
        if (input && input.value) return input.value;
        return null;
    }

    function injectButtons(challengeId) {
        var modal = document.getElementById("challenge-window");
        if (!modal) return;

        var existing = modal.querySelector(".discussion-plugin-btn-group");
        if (existing && existing.dataset.challengeId === String(challengeId)) return;
        if (existing) existing.remove();

        var footer = modal.querySelector(".modal-footer") ||
                      modal.querySelector(".modal-body") ||
                      modal;

        var buttonGroup = document.createElement("div");
        buttonGroup.className = "discussion-plugin-btn-group d-flex flex-wrap gap-2 mt-3";
        buttonGroup.dataset.challengeId = challengeId;

        function makeBtn(label, icon, cls, url) {
            var a = document.createElement("a");
            a.href = url;
            a.className = "btn btn-sm discussion-plugin-btn " + cls;
            a.style.marginLeft = "6px";
            var iconEl = document.createElement("i");
            iconEl.className = "fas " + icon;
            a.append(iconEl, document.createTextNode(" " + label));
            return a;
        }

        var challengesRoot = window.location.pathname.endsWith("/") ? window.location.pathname.slice(0, -1) : window.location.pathname;
        buttonGroup.appendChild(makeBtn("General discussion", "fa-comments", "btn-outline-info", challengesRoot + "/" + challengeId + "/discuss/general"));
        buttonGroup.appendChild(makeBtn("Post solution", "fa-lock", "btn-outline-warning", challengesRoot + "/" + challengeId + "/discuss/spoiler"));
        buttonGroup.appendChild(makeBtn("Writeup", "fa-pen-to-square", "btn-outline-success", challengesRoot + "/" + challengeId + "/discuss/writeup"));
        footer.appendChild(buttonGroup);
    }

    function ensureButtons() {
        var id = getChallengeId();
        if (id) injectButtons(id);
    }

    document.addEventListener("shown.bs.modal", function (e) {
        if (!e.target || e.target.id !== "challenge-window") return;
        setTimeout(ensureButtons, 50);
    });

    // CTFd replaces this modal's content with Alpine after challenge data loads.
    // Observe that replacement so the controls are present even if it happens
    // after Bootstrap has emitted its shown event.
    var modal = document.getElementById("challenge-window");
    if (modal) {
        new MutationObserver(ensureButtons).observe(modal, { childList: true, subtree: true });
    }
})();
