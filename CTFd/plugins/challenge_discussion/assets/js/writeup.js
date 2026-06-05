/**
 * writeup.js
 *
 * Handles the student writeup page (/challenges/<id>/discuss/writeup).
 *
 * Expects these globals to be set by the template before this script loads:
 *   CHALLENGE_ID, CURRENT_USER_ID, IS_ADMIN, CSRF_TOKEN
 */
(function () {
  "use strict";

  // -------------------------------------------------------------------------
  // Utilities
  // -------------------------------------------------------------------------

  function renderMarkdown(text) {
    if (window.marked) {
      return marked.parse(text || "", { breaks: true, gfm: true });
    }
    var d = document.createElement("div");
    d.appendChild(document.createTextNode(text || ""));
    return "<span style='white-space:pre-wrap'>" + d.innerHTML + "</span>";
  }

  function escapeHtml(text) {
    var d = document.createElement("div");
    d.appendChild(document.createTextNode(text || ""));
    return d.innerHTML;
  }

  function formatDate(iso) {
    return new Date(iso).toLocaleString();
  }

  function scoreColor(score, max) {
    if (max === 0) return "#6c757d";
    var ratio = score / max;
    if (ratio >= 0.8) return "#198754";
    if (ratio >= 0.5) return "#ffc107";
    return "#dc3545";
  }

  // -------------------------------------------------------------------------
  // Render a score bar for a single criterion
  // -------------------------------------------------------------------------

  function buildScoreBarHtml(name, score, max) {
    var pct = max > 0 ? Math.round((score / max) * 100) : 0;
    var color = scoreColor(score, max);
    return (
      '<div class="mb-2">' +
        '<div class="d-flex justify-content-between mb-1">' +
          '<span class="small fw-semibold">' + escapeHtml(name) + '</span>' +
          '<span class="small fw-bold" style="color:' + color + '">' + score + ' / ' + max + '</span>' +
        '</div>' +
        '<div class="progress" style="height:8px;">' +
          '<div class="progress-bar" role="progressbar"' +
            ' style="width:' + pct + '%;background-color:' + color + ';"' +
            ' aria-valuenow="' + score + '" aria-valuemin="0" aria-valuemax="' + max + '">' +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  // -------------------------------------------------------------------------
  // Render the full review block (used for both own and others' writeups)
  // -------------------------------------------------------------------------

  function buildReviewHtml(review) {
    if (!review) return "";

    var scoresHtml = "";
    if (review.scores && review.scores.length) {
      review.scores.forEach(function (s) {
        scoresHtml += buildScoreBarHtml(s.name, s.score, s.max_score);
      });
    }

    var totalColor = scoreColor(review.total_score, review.max_score);
    var commentHtml = review.comment
      ? '<div class="mt-3 pt-2 border-top">' +
          '<p class="mb-1 small text-muted fw-semibold text-uppercase">Teacher Comment</p>' +
          '<p class="mb-0 fst-italic">' + escapeHtml(review.comment) + "</p>" +
        "</div>"
      : "";

    return (
      '<div class="mt-3 p-3 rounded border" style="background:#f8fff9;">' +
        '<p class="mb-2 small text-muted fw-semibold text-uppercase">' +
          '<i class="fas fa-star text-warning"></i> Teacher Feedback' +
        "</p>" +
        scoresHtml +
        '<div class="d-flex justify-content-between align-items-center mt-2 pt-2 border-top">' +
          '<strong>Total</strong>' +
          '<span class="fs-6 fw-bold" style="color:' + totalColor + '">' +
            review.total_score + " / " + review.max_score +
          "</span>" +
        "</div>" +
        commentHtml +
      "</div>"
    );
  }

  // -------------------------------------------------------------------------
  // Render the "All reviewed writeups" list
  // -------------------------------------------------------------------------

  function renderAllWriteups(submissions) {
    var container = document.getElementById("all-writeups-list");
    var reviewed = submissions.filter(function (s) {
      return s.status === "reviewed" && s.user_id !== CURRENT_USER_ID;
    });

    document.getElementById("reviewed-count").textContent = reviewed.length;

    if (!reviewed.length) {
      container.innerHTML =
        '<p class="text-muted text-center py-4">No reviewed writeups yet.</p>';
      return;
    }

    container.innerHTML = reviewed
      .map(function (sub) {
        return (
          '<div class="card mb-4">' +
            '<div class="card-header d-flex justify-content-between align-items-center">' +
              '<span><i class="fas fa-user me-1"></i><strong>' +
                escapeHtml(sub.username) +
              "</strong></span>" +
              '<small class="text-muted">' + formatDate(sub.created_at) + "</small>" +
            "</div>" +
            '<div class="card-body">' +
              '<div class="markdown-body mb-3">' + renderMarkdown(sub.content) + "</div>" +
              buildReviewHtml(sub.review) +
            "</div>" +
          "</div>"
        );
      })
      .join("");
  }

  // -------------------------------------------------------------------------
  // Render own writeup section
  // -------------------------------------------------------------------------

  function renderOwnWriteup(sub) {
    var editor = document.getElementById("writeup-editor");
    var reviewed = document.getElementById("writeup-reviewed");
    var badge = document.getElementById("writeup-status-badge");

    if (!sub) {
      // No writeup yet — show empty editor
      editor.classList.remove("d-none");
      reviewed.classList.add("d-none");
      badge.innerHTML = '<span class="badge bg-secondary">Not submitted</span>';
      return;
    }

    if (sub.status === "reviewed") {
      // Lock editor, show rendered content + review
      editor.classList.add("d-none");
      reviewed.classList.remove("d-none");
      badge.innerHTML = '<span class="badge bg-success">Reviewed</span>';

      document.getElementById("writeup-content-rendered").innerHTML =
        renderMarkdown(sub.content);

      if (sub.review) {
        // Populate per-criterion score bars
        var scoresContainer = document.getElementById("review-criteria-scores");
        scoresContainer.innerHTML = "";
        if (sub.review.scores && sub.review.scores.length) {
          sub.review.scores.forEach(function (s) {
            scoresContainer.innerHTML += buildScoreBarHtml(s.name, s.score, s.max_score);
          });
        }
        // Total
        var totalColor = scoreColor(sub.review.total_score, sub.review.max_score);
        document.getElementById("review-total-score").textContent =
          sub.review.total_score + " / " + sub.review.max_score;
        document.getElementById("review-total-score").style.color = totalColor;
        // Comment
        if (sub.review.comment) {
          document.getElementById("review-comment-block").classList.remove("d-none");
          document.getElementById("review-comment-text").textContent = sub.review.comment;
        }
      }
    } else {
      // Draft — show editor pre-filled
      editor.classList.remove("d-none");
      reviewed.classList.add("d-none");
      badge.innerHTML = '<span class="badge bg-warning text-dark">Draft</span>';
      document.getElementById("writeup-content").value = sub.content;
    }
  }

  // -------------------------------------------------------------------------
  // Save writeup
  // -------------------------------------------------------------------------

  document.getElementById("writeup-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var content = document.getElementById("writeup-content").value.trim();
    if (!content) return;

    var btn = document.getElementById("writeup-save-btn");
    var status = document.getElementById("writeup-save-status");
    btn.disabled = true;
    status.textContent = "Saving…";

    fetch("/api/v1/discussion/writeups", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "CSRF-Token": CSRF_TOKEN,
      },
      body: JSON.stringify({ challenge_id: CHALLENGE_ID, content: content }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        btn.disabled = false;
        if (data.success) {
          status.textContent = "Saved " + new Date().toLocaleTimeString();
          renderOwnWriteup(data.data);
        } else {
          status.textContent = "";
          alert(data.errors || "Save failed");
        }
      })
      .catch(function () {
        btn.disabled = false;
        status.textContent = "";
        alert("Network error. Please try again.");
      });
  });

  // -------------------------------------------------------------------------
  // Initial page load
  // -------------------------------------------------------------------------

  function loadPage() {
    // Load own writeup
    fetch("/api/v1/discussion/writeups/my?challenge_id=" + CHALLENGE_ID)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) renderOwnWriteup(data.data);
      });

    // Load all writeups for the reviewed list
    fetch("/api/v1/discussion/writeups?challenge_id=" + CHALLENGE_ID)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) renderAllWriteups(data.data);
        else
          document.getElementById("all-writeups-list").innerHTML =
            '<div class="alert alert-danger">' + escapeHtml(data.errors) + "</div>";
      });
  }

  loadPage();
})();
