"""
Challenge Discussion Plugin

Three independent pages per challenge:
- /challenges/<id>/discuss/general   — spoiler-free, open to all authenticated users
- /challenges/<id>/discuss/spoiler   — post-solve only (403 for unsolved users)
- /challenges/<id>/discuss/writeup   — post-solve writeup with rubric grading

Admin pages:
- /admin/discussion/rubric           — global rubric criteria management
- /admin/discussion/writeups         — grading queue (all submissions across challenges)
"""

import csv
import datetime
import io

from flask import Blueprint, jsonify, render_template, request, Response

from CTFd.models import Challenges, Solves, Users, db
from CTFd.plugins import register_plugin_assets_directory, register_plugin_script
from CTFd.plugins.migrations import upgrade
from CTFd.utils.decorators import admins_only, authed_only
from CTFd.utils.user import get_current_user


# ---------------------------------------------------------------------------
# Models — Discussion
# ---------------------------------------------------------------------------


class DiscussionPost(db.Model):
    __tablename__ = "challenge_discussion_posts"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # "general" or "spoiler"
    post_type = db.Column(db.String(16), nullable=False, default="general")
    parent_id = db.Column(
        db.Integer,
        db.ForeignKey("challenge_discussion_posts.id", ondelete="CASCADE"),
        nullable=True,
    )
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    hidden = db.Column(db.Boolean, default=False)

    challenge = db.relationship("Challenges", foreign_keys=[challenge_id], lazy="select")
    user = db.relationship("Users", foreign_keys=[user_id], lazy="select")
    replies = db.relationship(
        "DiscussionPost",
        backref=db.backref("parent", remote_side=[id]),
        lazy="dynamic",
        foreign_keys=[parent_id],
    )


# ---------------------------------------------------------------------------
# Models — Writeup system
# ---------------------------------------------------------------------------


class WriteupRubricCriterion(db.Model):
    """Global rubric criteria — same for every challenge."""

    __tablename__ = "writeup_rubric_criteria"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    max_score = db.Column(db.Integer, nullable=False, default=10)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "max_score": self.max_score,
            "display_order": self.display_order,
        }


class WriteupSubmission(db.Model):
    """One writeup per student per challenge."""

    __tablename__ = "writeup_submissions"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content = db.Column(db.Text, nullable=False)
    # 'draft' → student can still edit; 'reviewed' → locked
    status = db.Column(db.String(16), nullable=False, default="draft")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint("challenge_id", "user_id", name="uq_writeup_challenge_user"),
    )

    challenge = db.relationship("Challenges", foreign_keys=[challenge_id], lazy="select")
    user = db.relationship("Users", foreign_keys=[user_id], lazy="select")
    review = db.relationship(
        "WriteupReview", back_populates="submission", uselist=False, lazy="select"
    )

    def serialize(self, include_review=False):
        data = {
            "id": self.id,
            "challenge_id": self.challenge_id,
            "user_id": self.user_id,
            "username": self.user.name if self.user else "deleted",
            "content": self.content,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_review and self.review:
            data["review"] = self.review.serialize()
        elif self.review:
            # Lightweight review summary (total score only)
            data["review"] = {
                "total_score": self.review.total_score,
                "max_score": self.review.max_score,
            }
        else:
            data["review"] = None
        return data


class WriteupReview(db.Model):
    """One review per submission, created by an admin."""

    __tablename__ = "writeup_reviews"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(
        db.Integer,
        db.ForeignKey("writeup_submissions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    reviewer_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # {str(criterion_id): score, ...}
    scores = db.Column(db.JSON, nullable=False, default=dict)
    comment = db.Column(db.Text, nullable=True)
    # Snapshot totals — preserved even if criteria are later edited
    total_score = db.Column(db.Integer, nullable=False, default=0)
    max_score = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    submission = db.relationship(
        "WriteupSubmission", back_populates="review", lazy="select"
    )
    reviewer = db.relationship("Users", foreign_keys=[reviewer_id], lazy="select")

    def serialize(self):
        criteria = (
            WriteupRubricCriterion.query.order_by(
                WriteupRubricCriterion.display_order
            ).all()
        )
        criterion_scores = []
        for c in criteria:
            criterion_scores.append(
                {
                    "criterion_id": c.id,
                    "name": c.name,
                    "score": self.scores.get(str(c.id), 0),
                    "max_score": c.max_score,
                }
            )
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "reviewer_id": self.reviewer_id,
            "reviewer": self.reviewer.name if self.reviewer else "deleted",
            "scores": criterion_scores,
            "comment": self.comment or "",
            "total_score": self.total_score,
            "max_score": self.max_score,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def user_has_solved(user_id, challenge_id):
    return (
        Solves.query.filter_by(user_id=user_id, challenge_id=challenge_id).first()
        is not None
    )


def _serialize_post(p):
    return {
        "id": p.id,
        "user_id": p.user_id,
        "username": p.user.name if p.user else "deleted",
        "content": p.content,
        "date": p.date.isoformat(),
        "replies": [
            _serialize_post(r)
            for r in p.replies.filter_by(hidden=False).order_by(
                DiscussionPost.date.asc()
            )
        ],
    }


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

discussion_bp = Blueprint(
    "challenge_discussion",
    __name__,
    template_folder="templates",
    static_folder="assets",
    static_url_path="/plugins/challenge_discussion/assets",
)


# ---------------------------------------------------------------------------
# Page routes — Discussion (existing)
# ---------------------------------------------------------------------------


@discussion_bp.route("/challenges/<int:challenge_id>/discuss/general")
@authed_only
def discuss_general(challenge_id):
    challenge = Challenges.query.filter_by(id=challenge_id, state="visible").first_or_404()
    user = get_current_user()
    return render_template("discuss_general.html", challenge=challenge, user=user)


@discussion_bp.route("/challenges/<int:challenge_id>/discuss/spoiler")
@authed_only
def discuss_spoiler(challenge_id):
    challenge = Challenges.query.filter_by(id=challenge_id, state="visible").first_or_404()
    user = get_current_user()
    solved = user_has_solved(user.id, challenge_id) or user.type == "admin"
    if not solved:
        return render_template("discuss_locked.html", challenge=challenge, user=user), 403
    return render_template("discuss_spoiler.html", challenge=challenge, user=user)


# ---------------------------------------------------------------------------
# Page routes — Writeup (new)
# ---------------------------------------------------------------------------


@discussion_bp.route("/challenges/<int:challenge_id>/discuss/writeup")
@authed_only
def discuss_writeup(challenge_id):
    challenge = Challenges.query.filter_by(id=challenge_id, state="visible").first_or_404()
    user = get_current_user()
    solved = user_has_solved(user.id, challenge_id) or user.type == "admin"
    if not solved:
        return render_template("discuss_locked.html", challenge=challenge, user=user), 403
    criteria = WriteupRubricCriterion.query.order_by(
        WriteupRubricCriterion.display_order
    ).all()
    return render_template(
        "discuss_writeup.html",
        challenge=challenge,
        user=user,
        criteria=criteria,
    )


@discussion_bp.route("/admin/discussion/rubric")
@admins_only
def admin_rubric():
    criteria = WriteupRubricCriterion.query.order_by(
        WriteupRubricCriterion.display_order
    ).all()
    return render_template("admin_rubric.html", criteria=criteria)


@discussion_bp.route("/admin/discussion/writeups")
@admins_only
def admin_writeup_queue():
    challenges = (
        Challenges.query.filter_by(state="visible")
        .order_by(Challenges.category, Challenges.name)
        .all()
    )
    criteria = WriteupRubricCriterion.query.order_by(
        WriteupRubricCriterion.display_order
    ).all()
    return render_template(
        "admin_writeup_queue.html",
        challenges=challenges,
        criteria=criteria,
        criteria_json=[c.serialize() for c in criteria],
    )


# ---------------------------------------------------------------------------
# REST API — Discussion posts (existing, unchanged)
# ---------------------------------------------------------------------------


@discussion_bp.route("/api/v1/discussion/posts", methods=["GET"])
@authed_only
def list_posts():
    challenge_id = request.args.get("challenge_id", type=int)
    post_type = request.args.get("type")

    if not challenge_id or post_type not in ("general", "spoiler"):
        return jsonify({"success": False, "errors": "challenge_id and valid type required"}), 400

    challenge = Challenges.query.filter_by(id=challenge_id, state="visible").first()
    if not challenge:
        return jsonify({"success": False, "errors": "Challenge not found"}), 404

    user = get_current_user()
    if (
        post_type == "spoiler"
        and not user_has_solved(user.id, challenge_id)
        and user.type != "admin"
    ):
        return jsonify({"success": False, "errors": "You must solve this challenge first."}), 403

    posts = (
        DiscussionPost.query.filter_by(
            challenge_id=challenge_id, post_type=post_type, parent_id=None, hidden=False
        )
        .order_by(DiscussionPost.date.asc())
        .all()
    )
    return jsonify({"success": True, "data": [_serialize_post(p) for p in posts]})


@discussion_bp.route("/api/v1/discussion/posts", methods=["POST"])
@authed_only
def create_post():
    data = request.get_json(silent=True) or request.form

    try:
        challenge_id = int(data.get("challenge_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "errors": "challenge_id required"}), 400

    content = (data.get("content") or "").strip()
    post_type = data.get("post_type") or "general"
    parent_id = data.get("parent_id") or None

    if not content:
        return jsonify({"success": False, "errors": "content required"}), 400
    if post_type not in ("general", "spoiler"):
        return jsonify({"success": False, "errors": "invalid post_type"}), 400

    challenge = Challenges.query.filter_by(id=challenge_id, state="visible").first()
    if not challenge:
        return jsonify({"success": False, "errors": "Challenge not found"}), 404

    user = get_current_user()

    if parent_id:
        parent = DiscussionPost.query.filter_by(
            id=parent_id, challenge_id=challenge_id, hidden=False
        ).first()
        if not parent:
            return jsonify({"success": False, "errors": "Parent post not found"}), 404
        post_type = parent.post_type  # inherit from parent

    if (
        post_type == "spoiler"
        and not user_has_solved(user.id, challenge_id)
        and user.type != "admin"
    ):
        return jsonify({"success": False, "errors": "You must solve this challenge first."}), 403

    post = DiscussionPost(
        challenge_id=challenge_id,
        user_id=user.id,
        post_type=post_type,
        parent_id=parent_id,
        content=content,
    )
    db.session.add(post)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "data": {
                "id": post.id,
                "user_id": post.user_id,
                "username": user.name,
                "post_type": post.post_type,
                "content": post.content,
                "date": post.date.isoformat(),
            },
        }
    )


@discussion_bp.route("/api/v1/discussion/posts/<int:post_id>", methods=["DELETE"])
@authed_only
def delete_post(post_id):
    post = DiscussionPost.query.get_or_404(post_id)
    user = get_current_user()
    if post.user_id != user.id and user.type != "admin":
        return jsonify({"success": False, "errors": "Forbidden"}), 403
    post.hidden = True
    db.session.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# REST API — Rubric criteria
# ---------------------------------------------------------------------------


@discussion_bp.route("/api/v1/discussion/rubric", methods=["GET"])
@authed_only
def list_rubric():
    criteria = WriteupRubricCriterion.query.order_by(
        WriteupRubricCriterion.display_order
    ).all()
    return jsonify({"success": True, "data": [c.serialize() for c in criteria]})


@discussion_bp.route("/api/v1/discussion/rubric", methods=["POST"])
@admins_only
def create_criterion():
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "errors": "name required"}), 400
    try:
        max_score = int(data.get("max_score", 10))
        if max_score < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"success": False, "errors": "max_score must be a positive integer"}), 400

    last = (
        WriteupRubricCriterion.query.order_by(
            WriteupRubricCriterion.display_order.desc()
        ).first()
    )
    next_order = (last.display_order + 1) if last else 0

    criterion = WriteupRubricCriterion(
        name=name,
        description=(data.get("description") or "").strip() or None,
        max_score=max_score,
        display_order=next_order,
    )
    db.session.add(criterion)
    db.session.commit()
    return jsonify({"success": True, "data": criterion.serialize()}), 201


@discussion_bp.route("/api/v1/discussion/rubric/<int:criterion_id>", methods=["PATCH"])
@admins_only
def update_criterion(criterion_id):
    criterion = WriteupRubricCriterion.query.get_or_404(criterion_id)
    data = request.get_json(silent=True) or request.form
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify({"success": False, "errors": "name cannot be empty"}), 400
        criterion.name = name
    if "description" in data:
        criterion.description = (data["description"] or "").strip() or None
    if "max_score" in data:
        try:
            max_score = int(data["max_score"])
            if max_score < 1:
                raise ValueError
            criterion.max_score = max_score
        except (TypeError, ValueError):
            return jsonify({"success": False, "errors": "max_score must be a positive integer"}), 400
    if "display_order" in data:
        try:
            criterion.display_order = int(data["display_order"])
        except (TypeError, ValueError):
            pass
    db.session.commit()
    return jsonify({"success": True, "data": criterion.serialize()})


@discussion_bp.route("/api/v1/discussion/rubric/<int:criterion_id>", methods=["DELETE"])
@admins_only
def delete_criterion(criterion_id):
    criterion = WriteupRubricCriterion.query.get_or_404(criterion_id)
    db.session.delete(criterion)
    db.session.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# REST API — Writeup submissions
# ---------------------------------------------------------------------------


@discussion_bp.route("/api/v1/discussion/writeups", methods=["GET"])
@authed_only
def list_writeups():
    """
    List writeup submissions for a challenge.

    Admin: all submissions, full review details.
    Solver: all submissions — content visible, review details (scores + comment)
            visible for reviewed writeups (both own and others).
    """
    challenge_id = request.args.get("challenge_id", type=int)
    if not challenge_id:
        return jsonify({"success": False, "errors": "challenge_id required"}), 400

    challenge = Challenges.query.filter_by(id=challenge_id, state="visible").first()
    if not challenge:
        return jsonify({"success": False, "errors": "Challenge not found"}), 404

    user = get_current_user()
    is_admin = user.type == "admin"

    if not is_admin and not user_has_solved(user.id, challenge_id):
        return jsonify({"success": False, "errors": "You must solve this challenge first."}), 403

    submissions = (
        WriteupSubmission.query.filter_by(challenge_id=challenge_id)
        .order_by(WriteupSubmission.created_at.asc())
        .all()
    )

    result = []
    for sub in submissions:
        if is_admin:
            # Admin always gets full review details
            result.append(sub.serialize(include_review=True))
        else:
            # Students see content for all, full review for reviewed writeups
            data = {
                "id": sub.id,
                "challenge_id": sub.challenge_id,
                "user_id": sub.user_id,
                "username": sub.user.name if sub.user else "deleted",
                "content": sub.content,
                "status": sub.status,
                "created_at": sub.created_at.isoformat(),
                "updated_at": sub.updated_at.isoformat() if sub.updated_at else None,
            }
            if sub.review:
                # Full review visible to all solvers once graded
                data["review"] = sub.review.serialize()
            else:
                data["review"] = None
            result.append(data)

    return jsonify({"success": True, "data": result})


@discussion_bp.route("/api/v1/discussion/writeups/my", methods=["GET"])
@authed_only
def get_my_writeup():
    """Return the current user's writeup for a specific challenge."""
    challenge_id = request.args.get("challenge_id", type=int)
    if not challenge_id:
        return jsonify({"success": False, "errors": "challenge_id required"}), 400

    user = get_current_user()
    if not user_has_solved(user.id, challenge_id) and user.type != "admin":
        return jsonify({"success": False, "errors": "You must solve this challenge first."}), 403

    sub = WriteupSubmission.query.filter_by(
        challenge_id=challenge_id, user_id=user.id
    ).first()
    if not sub:
        return jsonify({"success": True, "data": None})
    return jsonify({"success": True, "data": sub.serialize(include_review=True)})


@discussion_bp.route("/api/v1/discussion/writeups", methods=["POST"])
@authed_only
def save_writeup():
    """Create or update the current user's writeup. Blocked once reviewed."""
    data = request.get_json(silent=True) or request.form

    try:
        challenge_id = int(data.get("challenge_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "errors": "challenge_id required"}), 400

    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"success": False, "errors": "content required"}), 400

    challenge = Challenges.query.filter_by(id=challenge_id, state="visible").first()
    if not challenge:
        return jsonify({"success": False, "errors": "Challenge not found"}), 404

    user = get_current_user()
    if not user_has_solved(user.id, challenge_id) and user.type != "admin":
        return jsonify({"success": False, "errors": "You must solve this challenge first."}), 403

    sub = WriteupSubmission.query.filter_by(
        challenge_id=challenge_id, user_id=user.id
    ).first()

    if sub:
        if sub.status == "reviewed":
            return jsonify(
                {"success": False, "errors": "Your writeup has already been reviewed and cannot be edited."}
            ), 403
        sub.content = content
        sub.updated_at = datetime.datetime.utcnow()
    else:
        sub = WriteupSubmission(
            challenge_id=challenge_id,
            user_id=user.id,
            content=content,
        )
        db.session.add(sub)

    db.session.commit()
    return jsonify({"success": True, "data": sub.serialize(include_review=True)})


@discussion_bp.route("/api/v1/discussion/writeups/<int:submission_id>", methods=["DELETE"])
@admins_only
def delete_writeup(submission_id):
    """Admin: hard-delete a submission and its review."""
    sub = WriteupSubmission.query.get_or_404(submission_id)
    db.session.delete(sub)
    db.session.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# REST API — Writeup reviews
# ---------------------------------------------------------------------------


@discussion_bp.route(
    "/api/v1/discussion/writeups/<int:submission_id>/review", methods=["POST"]
)
@admins_only
def submit_review(submission_id):
    """Create or update a review for a writeup submission."""
    sub = WriteupSubmission.query.get_or_404(submission_id)
    data = request.get_json(silent=True) or request.form

    scores_raw = data.get("scores")
    if not isinstance(scores_raw, dict):
        return jsonify({"success": False, "errors": "scores must be a JSON object {criterion_id: score}"}), 400

    criteria = WriteupRubricCriterion.query.all()
    criteria_map = {c.id: c for c in criteria}

    validated_scores = {}
    total = 0
    max_total = 0
    for c in criteria:
        raw = scores_raw.get(str(c.id))
        try:
            score = int(raw) if raw is not None else 0
            score = max(0, min(score, c.max_score))
        except (TypeError, ValueError):
            score = 0
        validated_scores[str(c.id)] = score
        total += score
        max_total += c.max_score

    comment = (data.get("comment") or "").strip()
    user = get_current_user()

    review = WriteupReview.query.filter_by(submission_id=submission_id).first()
    if review:
        review.scores = validated_scores
        review.comment = comment or None
        review.total_score = total
        review.max_score = max_total
        review.updated_at = datetime.datetime.utcnow()
    else:
        review = WriteupReview(
            submission_id=submission_id,
            reviewer_id=user.id,
            scores=validated_scores,
            comment=comment or None,
            total_score=total,
            max_score=max_total,
        )
        db.session.add(review)

    sub.status = "reviewed"
    db.session.commit()
    return jsonify({"success": True, "data": review.serialize()})


# ---------------------------------------------------------------------------
# REST API — Grade export (CSV)
# ---------------------------------------------------------------------------


@discussion_bp.route("/api/v1/discussion/grades/export", methods=["GET"])
@admins_only
def export_grades():
    """
    Export writeup grades as CSV.
    Optional query param: challenge_id — filter to a single challenge.
    """
    challenge_id = request.args.get("challenge_id", type=int)

    criteria = WriteupRubricCriterion.query.order_by(
        WriteupRubricCriterion.display_order
    ).all()

    query = WriteupSubmission.query.filter_by(status="reviewed")
    if challenge_id:
        query = query.filter_by(challenge_id=challenge_id)
    submissions = query.order_by(
        WriteupSubmission.challenge_id, WriteupSubmission.user_id
    ).all()

    output = io.StringIO()
    fieldnames = (
        ["challenge", "username"]
        + [c.name for c in criteria]
        + ["total", "max", "comment"]
    )
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for sub in submissions:
        if not sub.review:
            continue
        row = {
            "challenge": sub.challenge.name if sub.challenge else str(sub.challenge_id),
            "username": sub.user.name if sub.user else "deleted",
            "total": sub.review.total_score,
            "max": sub.review.max_score,
            "comment": sub.review.comment or "",
        }
        for c in criteria:
            row[c.name] = sub.review.scores.get(str(c.id), 0)
        writer.writerow(row)

    csv_bytes = output.getvalue().encode("utf-8")
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=writeup_grades.csv"},
    )


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------


def load(app):
    upgrade(plugin_name="challenge_discussion")
    with app.app_context():
        db.create_all()
    app.register_blueprint(discussion_bp)
    register_plugin_assets_directory(app, base_path="/plugins/challenge_discussion/assets/")
    register_plugin_script("/plugins/challenge_discussion/assets/js/discussion.js")
