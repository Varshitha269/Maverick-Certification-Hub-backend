import sys
import datetime as dt
sys.path.insert(0, '.')
from app.db.session import SessionLocal
from app.models.user import User
from app.models.certification import Certification
from app.models.enrollment import Enrollment, EnrollmentStatus

db = SessionLocal()

user_email = "varshithagovindaswamy@gmail.com"
user = db.query(User).filter(User.email == user_email).first()

if not user:
    print(f"User {user_email} not found.")
    sys.exit(1)

# Certifications we just added
target_certs = [
    "PCEP - Certified Entry-Level Python Programmer",
    "Microsoft Certified: C# Developer",
    "AWS Certified Solutions Architect - Associate"
]

added = 0
for title in target_certs:
    cert = db.query(Certification).filter(Certification.title == title).first()
    if cert:
        # Check if enrollment already exists
        enr = db.query(Enrollment).filter(Enrollment.user_id == user.id, Enrollment.certification_id == cert.id).first()
        if not enr:
            enr = Enrollment(
                user_id=user.id,
                certification_id=cert.id,
                status=EnrollmentStatus.completed,
                progress_percent=100,
                created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10),
                updated_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
            )
            db.add(enr)
            added += 1
        else:
            enr.status = EnrollmentStatus.completed
            enr.progress_percent = 100
            enr.updated_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
            added += 1

db.commit()
print(f"Successfully seeded {added} completed enrollments for {user_email}.")
db.close()
