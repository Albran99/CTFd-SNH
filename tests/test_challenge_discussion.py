from CTFd.models import db
from CTFd.plugins.challenge_discussion import (
    WriteupReview,
    WriteupRevision,
    WriteupRubricCriterion,
    WriteupSubmission,
)
from tests.helpers import (
    create_ctfd,
    destroy_ctfd,
    gen_challenge,
    gen_solve,
    gen_user,
    login_as_user,
)


def test_reviewed_writeup_can_be_resubmitted_with_feedback_history():
    app = create_ctfd(enable_plugins=True)
    with app.app_context():
        user = gen_user(app.db, name="writer")
        challenge = gen_challenge(app.db)
        gen_solve(app.db, user_id=user.id, challenge_id=challenge.id)

        criterion = WriteupRubricCriterion(name="Clarity", max_score=10)
        submission = WriteupSubmission(
            challenge_id=challenge.id,
            user_id=user.id,
            content="Original explanation",
            status="reviewed",
        )
        db.session.add_all([criterion, submission])
        db.session.flush()
        db.session.add(
            WriteupReview(
                submission_id=submission.id,
                reviewer_id=1,
                scores={str(criterion.id): 7},
                comment="Explain the final step.",
                total_score=7,
                max_score=10,
            )
        )
        db.session.commit()

        client = login_as_user(app, name="writer")
        response = client.post(
            "/api/v1/discussion/writeups",
            json={
                "challenge_id": challenge.id,
                "content": "Revised explanation with the final step.",
            },
        )

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["status"] == "draft"
        assert data["review"] is None
        assert len(data["previous_versions"]) == 1
        assert data["previous_versions"][0]["content"] == "Original explanation"
        assert data["previous_versions"][0]["review"]["comment"] == "Explain the final step."

        assert WriteupRevision.query.filter_by(submission_id=submission.id).count() == 1
        assert WriteupReview.query.filter_by(submission_id=submission.id).first() is None
        assert WriteupSubmission.query.get(submission.id).content == "Revised explanation with the final step."

    destroy_ctfd(app)
