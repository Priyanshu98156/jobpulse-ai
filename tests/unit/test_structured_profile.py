import pytest
from app.db.session import SessionLocal
from app.db.models import (
    CandidateIdentity,
    WorkExperience,
    Education,
    Project,
    Skill,
    SearchProfile,
    AnswerBank,
)

def test_candidate_identity_lifecycle_and_encryption():
    db = SessionLocal()
    try:
        # Create candidate with encrypted PII
        candidate = CandidateIdentity(
            full_name="Mahadev Testing",
            email="secret.mahadev@example.com",
            phone="+91-9876543210",
            location="Bengaluru, India",
            citizenship="India",
            work_authorization="Authorized in India / US Remote B2B",
            notice_period="30 Days",
            expected_salary="$85,000 / year",
            summary="Full Stack ML Engineer"
        )
        db.add(candidate)
        db.flush()

        # Add relational experience
        exp = WorkExperience(
            candidate_id=candidate.id,
            company="Enterprise AI Corp",
            title="Senior AI Engineer",
            location="Remote",
            is_remote=True,
            start_date="2022-03",
            end_date="Present",
            is_current=True,
            bullet_points=["Architected multi-provider LLM orchestration system", "Reduced latency by 45%"]
        )
        db.add(exp)

        # Add AnswerBank entries (one factual, one narrative)
        ans_factual = AnswerBank(
            candidate_id=candidate.id,
            question_pattern="require sponsorship",
            answer_text="No, I do not require sponsorship for India or B2B contractor roles.",
            category="legal",
            is_factual=True,
            source="user_verified"
        )
        db.add(ans_factual)
        db.commit()

        # Query back and verify relations & transparent decryption
        retrieved = db.query(CandidateIdentity).filter(CandidateIdentity.id == candidate.id).first()
        assert retrieved is not None
        assert retrieved.full_name == "Mahadev Testing"
        # Decrypted automatically via EncryptedText TypeDecorator
        assert retrieved.email == "secret.mahadev@example.com"
        assert retrieved.phone == "+91-9876543210"
        assert retrieved.expected_salary == "$85,000 / year"

        # Check relationships
        assert len(retrieved.experiences) >= 1
        assert retrieved.experiences[0].company == "Enterprise AI Corp"
        assert len(retrieved.experiences[0].bullet_points) == 2

        assert len(retrieved.answers) >= 1
        assert retrieved.answers[0].is_factual is True

        # Clean up test candidate
        db.delete(retrieved)
        db.commit()
    finally:
        db.close()
