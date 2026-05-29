"""
Challenge Discussion Plugin

Two independent discussion pages per challenge:
- /challenges/<id>/discuss/general  — spoiler-free, open to all authenticated users
- /challenges/<id>/discuss/spoiler  — post-solve only (403 for unsolved users)
"""

import datetime

from flask import Blueprint, jsonify, render_template, request

from CTFd.models import Challenges, Solves, db
from CTFd.plugins import register_plugin_assets_directory, register_plugin_script
from CTFd.plugins.migrations import upgrade
from CTFd.utils.decorators import authed_only
from CTFd.utils.user import get_current_user


# ---------------------------------------------------------------------------
# Model
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
# Helpers
# ---------------------------------------------------------------------------


def user_has_solved(user_id, challenge_id):
    return Solves.query.filter_by(user_id=user_id, challenge_id=challenge_id).first() is not None


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
# Page routes
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
# REST API
# ---------------------------------------------------------------------------


def _serialize(p):
    return {
        "id": p.id,
        "user_id": p.user_id,
        "username": p.user.name if p.user else "deleted",
        "content": p.content,
        "date": p.date.isoformat(),
        "replies": [
            _serialize(r)
            for r in p.replies.filter_by(hidden=False).order_by(DiscussionPost.date.asc())
        ],
    }


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
    if post_type == "spoiler" and not user_has_solved(user.id, challenge_id) and user.type != "admin":
        return jsonify({"success": False, "errors": "You must solve this challenge first."}), 403

    posts = (
        DiscussionPost.query
        .filter_by(challenge_id=challenge_id, post_type=post_type, parent_id=None, hidden=False)
        .order_by(DiscussionPost.date.asc())
        .all()
    )
    return jsonify({"success": True, "data": [_serialize(p) for p in posts]})


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

    if post_type == "spoiler" and not user_has_solved(user.id, challenge_id) and user.type != "admin":
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

    return jsonify({
        "success": True,
        "data": {
            "id": post.id,
            "user_id": post.user_id,
            "username": user.name,
            "post_type": post.post_type,
            "content": post.content,
            "date": post.date.isoformat(),
        },
    })


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
# Plugin entry point
# ---------------------------------------------------------------------------


def load(app):
    upgrade(plugin_name="challenge_discussion")
    with app.app_context():
        db.create_all()
    app.register_blueprint(discussion_bp)
    register_plugin_assets_directory(app, base_path="/plugins/challenge_discussion/assets/")
    register_plugin_script("/plugins/challenge_discussion/assets/js/discussion.js")
