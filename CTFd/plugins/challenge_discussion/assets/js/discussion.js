/**
 * challenge_discussion/assets/js/discussion.js
 *
 * Injects two buttons into the challenge modal footer that navigate
 * in the same tab:
 *   - "General"  → /challenges/{id}/discuss/general  (open to all)
 *   - "Spoiler"  → /challenges/{id}/discuss/spoiler  (solve-gated)
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
        return null;
    }

    function injectButtons(challengeId) {
        var modal = document.getElementById("challenge-window");
        if (!modal) return;

        modal.querySelectorAll(".discussion-plugin-btn").forEach(function (el) { el.remove(); });

        var footer = modal.querySelector(".modal-footer") ||
                     modal.querySelector(".modal-body") ||
                     modal;

        function makeBtn(label, icon, cls, url) {
            var a = document.createElement("a");
            a.href = url;
            a.className = "btn btn-sm discussion-plugin-btn " + cls;
            a.style.marginLeft = "6px";
            a.innerHTML = '<i class="fas ' + icon + '"></i> ' + label;
            return a;
        }

        footer.appendChild(makeBtn("General discussion",  "fa-comments", "btn-outline-info",    "/challenges/" + challengeId + "/discuss/general"));
        footer.appendChild(makeBtn("Post solution discussion",  "fa-lock",     "btn-outline-warning", "/challenges/" + challengeId + "/discuss/spoiler"));
    }

    document.addEventListener("shown.bs.modal", function (e) {
        if (!e.target || e.target.id !== "challenge-window") return;
        setTimeout(function () {
            var id = getChallengeId();
            if (id) injectButtons(id);
        }, 50);
    });
})();
